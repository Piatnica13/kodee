"""Public structured data from catalogue facts, without inferred stock or reviews."""
from urllib.parse import urljoin
import re
from flask import url_for
from db.product_editorial import EDITORIAL_DESCRIPTIONS, PUBLIC_NAMES, PHOTO_ALTS


def product_display_name(product):
    return PUBLIC_NAMES.get(product.slug, product.name)


def product_description(product):
    return EDITORIAL_DESCRIPTIONS.get(product.slug, product.descriptions or '')


def product_photo_alt(product, number):
    return PHOTO_ALTS.get(product.slug, {}).get(number, f'{product_display_name(product)} — фото {number}')


def product_gallery_images(product):
    images = sorted(product.images, key=lambda image: image.num)
    # Show a confirmed wrist photo early on mobile, where only one image is visible.
    if product.slug in {'samolet', 'begunok-mini'}:
        images.sort(key=lambda image: {1: 0, 4: 1, 2: 2, 3: 3}.get(image.num, 9))
    return images


def format_price(value):
    return f'{value:,}'.replace(',', ' ') if value else ''


def product_title(product):
    name = product_display_name(product)
    if product.category in {'Кулон', 'Бегунок'}:
        return f'{name} на нити | KoDee Desire'
    return f'{name} | KoDee Desire'


def product_meta_description(product):
    name = product_display_name(product)
    source = product_description(product).strip()
    sentence = re.split(r'(?<=[.!?])\s+', source, maxsplit=1)[0].strip()
    if not sentence:
        sentence = f'{name}: фотографии изделия и детали заказа у мастерской.'
    details = []
    if product.weight:
        details.append(f'вес {str(product.weight).replace(".", ",")} г')
    if product.price:
        details.append(f'цена {format_price(product.price)} ₸')
    facts = ', '.join(details)
    return f'{sentence.rstrip(".!?")}.' + (f' {facts.capitalize()}.' if facts else '')


def engraving_summary(product):
    if product.category != 'Монеточка':
        return ''
    name = product.name.lower()
    sides = 'с одной стороны' if 'с одной стороны' in name else (
        'с двух сторон' if 'с двух сторон' in name else '')
    if not sides:
        return ''
    details = [f'Гравировка {sides}']
    if product.weight:
        details.append(f'вес {str(product.weight).replace(".", ",")} г')
    return ' · '.join(details)


def product_schema(product):
    url = 'https://kodee.kz' + url_for('web.product', slug=product.slug)
    data = {'@context': 'https://schema.org', '@type': 'Product', '@id': url + '#product',
            'url': url, 'name': product_display_name(product), 'sku': str(product.id),
            'brand': {'@type': 'Brand', 'name': 'KoDee Desire'}}
    description = product_description(product).strip()
    if description:
        data['description'] = description
    if product.images:
        data['image'] = [urljoin('https://kodee.kz', image.img1)
                         for image in product_gallery_images(product)]
    if product.price and product.price > 0:
        data['offers'] = {'@type': 'Offer', 'url': url, 'price': product.price,
                          'priceCurrency': 'KZT'}
    return data
