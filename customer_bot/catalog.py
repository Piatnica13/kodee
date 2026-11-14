"""Product catalog backed by the same database and transaction as orders."""
from urllib.parse import urljoin
from sqlalchemy import select
from db.models import Product, Product_image


class Catalog:
    def __init__(self, store, public_url):
        self.store = store
        self.public_url = public_url.rstrip('/') + '/'

    def all(self):
        p, image = Product.__table__, Product_image.__table__
        query = select(p.c.id, p.c.name, p.c.price, p.c.category, p.c.concept,
                       p.c.descriptions, p.c.gold, p.c.weight, image.c.img1).select_from(
            p.outerjoin(image, (image.c.product_id == p.c.id) & (image.c.num == 1))
        ).where(p.c.active.is_(True), p.c.price > 0).order_by(p.c.id)
        conn = self.store.current_connection.get()
        if conn is None:
            raise RuntimeError('Catalog access requires a customer transaction')
        rows = conn.execute(query).mappings()
        return [dict(id=r['id'], name=r['name'] or '', price=r['price'],
                     category=r['category'] or 'Украшения', concept=r['concept'] or '',
                     description=r['descriptions'] or '', stock=max(0, r['gold'] or 0),
                     weight=r['weight'], image=urljoin(self.public_url, r['img1'])
                     if r['img1'] and r['img1'].startswith('/') and not r['img1'].startswith('//') else None)
                for r in rows]

    def get(self, product_id):
        return next((product for product in self.all() if product['id'] == product_id), None)
