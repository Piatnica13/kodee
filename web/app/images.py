"""Decode uploads before publishing them; use generated filenames only."""
from io import BytesIO
from contextlib import contextmanager
from pathlib import Path
import os
import tempfile
import warnings
from PIL import Image, ImageOps, UnidentifiedImageError
from flask import current_app

MAX_IMAGE_BYTES = 8 * 1024 * 1024
MAX_PIXELS = 20_000_000


def image_directory(slug):
    from slugify import slugify
    if not slug or slugify(slug) != slug or len(slug) > 100:
        raise ValueError('Некорректный адрес товара')
    configured = current_app.config.get('PRODUCT_IMAGES_DIR')
    root = Path(configured).resolve() if configured else Path(current_app.static_folder).resolve() / 'image' / 'productImgs'
    path = (root / slug).resolve()
    if path.parent != root.resolve():
        raise ValueError('Некорректный путь изображения')
    return path


def decode_image(data):
    if not data or len(data) > MAX_IMAGE_BYTES:
        raise ValueError('Изображение должно быть не больше 8 МБ')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(BytesIO(data)) as image:
                if image.format not in {'JPEG', 'PNG', 'WEBP'} or image.width * image.height > MAX_PIXELS:
                    raise ValueError('Допустимы JPEG, PNG, WEBP до 20 мегапикселей')
                image.load()
                image = ImageOps.exif_transpose(image).convert('RGB')
                output = BytesIO()
                image.save(output, format='WEBP', quality=90)
                return output.getvalue()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise ValueError('Файл не является корректным изображением') from None


@contextmanager
def publish_images(slug, images):
    """Restore the previous batch if file publishing or the DB commit fails."""
    if not images or len(images) > 4 or len({num for num, _ in images}) != len(images) or any(num not in range(1, 5) for num, _ in images):
        raise ValueError('Допустимы четыре изображения')
    encoded = [(num, decode_image(data)) for num, data in images]
    directory = image_directory(slug)
    directory.mkdir(parents=True, exist_ok=True)
    previous = {num: (directory / f'img{num}.webp').read_bytes() if (directory / f'img{num}.webp').exists() else None for num, _ in encoded}
    try:
        for num, data in encoded:
            _atomic_write(directory / f'img{num}.webp', data)
        yield
    except Exception:
        for num, data in previous.items():
            target = directory / f'img{num}.webp'
            if data is None:
                target.unlink(missing_ok=True)
            else:
                _atomic_write(target, data)
        raise


def _atomic_write(target, data):
    fd, name = tempfile.mkstemp(dir=target.parent, suffix='.tmp')
    try:
        with os.fdopen(fd, 'wb') as output:
            output.write(data)
        os.replace(name, target)
    finally:
        if os.path.exists(name):
            os.unlink(name)
