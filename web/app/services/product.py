from flask import session, current_app, abort
from db.models import Product, Product_image, db, Address
from sqlalchemy import cast, String
from web.app.security import current_user
from web.app.validation import positive_id, text
from web.app.images import publish_images, MAX_IMAGE_BYTES
from slugify import slugify


class ProductService:
    @staticmethod
    def get_user_basket(user):
        ids = [item[0] for item in (user.basket or []) if isinstance(item, list) and len(item) == 4]
        return Product.query.filter(Product.id.in_(ids), Product.active.is_(True)).all()

    @staticmethod
    def check_user_for_product_page(slug):
        product = Product.query.filter_by(slug=slug, active=True).first_or_404()
        user = current_user()
        return {'product': product, 'user': user or '',
                'address': Address.query.filter_by(person_id=user.id).first() if user else '',
                'favorite': (user.favourites or []) if user else []}

    @staticmethod
    def basket_user():
        user = current_user()
        if not user:
            abort(401, description='Для этого действия войдите в аккаунт')
        return user

    @staticmethod
    def requested_product(data):
        product_id = positive_id(data.get('product_id'))
        product = db.session.get(Product, product_id)
        if not product or not product.active:
            abort(404, description='Товар недоступен')
        return product

    @staticmethod
    def add_product_to_basket(data):
        user = ProductService.basket_user()
        product = ProductService.requested_product(data)
        color = text(data.get('color'), 'Цвет', 20).lower()
        size = text(data.get('size'), 'Размер', 30)
        material = text(data.get('material'), 'Материал', 40).lower()
        if color not in {'красный', 'черный'} or size not in {'Меньше 12 см', '12-14 см', '15-16 см', '17-18 см', 'Больше 18 см'} or material not in {'золото 585 (красное)', 'серебро 925', 'золото 585 (белое)', 'золото 585 (жёлтое)'}:
            raise ValueError('Выберите допустимые параметры товара')
        basket = list(user.basket or [])
        if any(item[0] == product.id for item in basket):
            return {'success': False, 'error': 'Товар уже в корзине'}
        user.basket = basket + [[product.id, color, size, material]]
        db.session.commit()
        return {'success': True, 'message': 'Товар успешно добавлен в корзину'}

    @staticmethod
    def delete_product_from_basket(user, data):
        product_id = positive_id(data.get('product_id'))
        previous = user.basket or []
        user.basket = [item for item in previous if item[0] != product_id]
        db.session.commit()
        return {'success': True, 'message': 'Товар удален'}

    @staticmethod
    def add_or_delete_favorite_product(data):
        user = ProductService.basket_user()
        product = ProductService.requested_product(data)
        favorites = list(user.favourites or [])
        if product.id in favorites:
            user.favourites = [pid for pid in favorites if pid != product.id]
            message = 'Товар удалён из избранного'
        else:
            user.favourites = favorites + [product.id]
            message = 'Товар добавлен в избранное'
        db.session.commit()
        return {'success': True, 'message': message}

    @staticmethod
    def trans_products_to_JS():
        all_products = Product.query.filter_by(active=True).all()

        product_list = []
        for product in all_products:
            product_list.append({
                "id": product.id,
                "name": product.name,
                "price": product.price,
                "concept": product.concept,
                "category": product.category,
                "slug": product.slug,
                "image": f"/static/image/productImgs/{product.slug}/img1.webp"
            })

        return product_list

    @staticmethod
    def search_product(data):
        query = data.get("query", "").strip()[:100]
        if not query:
            current_app.logger.debug("Пустой поисковый запрос.")
            return []

        products = Product.query.filter(
            (cast(Product.id, String).ilike(f"%{query}%")) |
            (Product.name.ilike(f"%{query.capitalize()}%")) # type: ignore
        ).filter_by(active=True).limit(10).all()

        current_app.logger.info(f"Найдено {len(products)} товаров по запросу '{query}'.")

        results = [{
            "id": p.id,
            "name": p.name,
            "price": p.price,
            "slug": p.slug,
            "image": p.image()
        } for p in products]

        return results

    @staticmethod
    def get_products_for_properties():
        products = Product.query.filter_by(active=True).limit(4).all()
        products_json = []
        for p in products:
            products_json.append({
                "@type": "Product",
                "name": p.name,
                "image": p.image(),
                "description": p.descriptions,
                "brand": {
                    "@type": "Brand",
                    "name": "KoDee Desire"
                },
                "offers": {
                    "@type": "Offer",
                    "priceCurrency": "KZT",
                    "price": p.price,
                    "availability": "https://schema.org/InStock"
                }
            })
        return products_json

    @staticmethod
    def add_imgs_for_product(data_files, data_form):
        name = text(data_form.get('productName'), 'Название товара', 100)
        candidates = Product.query.filter_by(name=name).with_for_update().limit(2).all()
        if len(candidates) > 1:
            raise ValueError('Несколько товаров с таким названием: укажите уникальный slug товара')
        product = candidates[0] if candidates else Product.query.filter_by(slug=slugify(name)).with_for_update().first()
        if not product:
            abort(404, description='Сначала создайте товар')
        images = [(num, data_files[f'img{num}'].stream.read(MAX_IMAGE_BYTES + 1))
                  for num in range(1, 5) if f'img{num}' in data_files and data_files[f'img{num}'].filename]
        if not images:
            raise ValueError('Выберите изображения')
        with publish_images(product.slug, images):
            for num, _ in images:
                Product_image.query.filter_by(product_id=product.id, num=num).delete()
                db.session.add(Product_image(num, product.id, f'/static/image/productImgs/{product.slug}/img{num}.webp'))
            db.session.commit()
        return {'status': 'ok', 'success': True}

    @staticmethod
    def get_product():
        products = Product.query.filter_by(active=True).order_by(Product.id.asc()).all()
        product_data = [
            {
            "id": p.id,
            "name": p.name,
            "price": p.price,
            "concept": p.concept,
            "category": p.category,
            "image": p.image(),
            "slug": p.slug
            }
            for p in products
        ]
        return product_data
