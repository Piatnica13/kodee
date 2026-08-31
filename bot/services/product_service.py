from db.models import Product

class ProductService:
    def get_all(self):
        return Product.query.order_by(Product.slug).all() # type: ignore

    
    def get_by_id(self, id):
        return Product.query.filter_by(id=id).first()

    