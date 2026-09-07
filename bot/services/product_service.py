from db.models import Product
from sqlalchemy import case, func



class ProductService:
    def get_all(self):
        concept_order = case(
            (Product.concept=="Знаки зодиака", 1), # type: ignore
            else_=0
        )

        return Product.query.order_by(concept_order, func.lower(Product.short_name)).all() # type: ignore

    
    def get_by_id_or_name(self, data):
        data = str(data).strip()
        
        if data.isdigit():
            return Product.query.filter_by(id=int(data)).first()


        return Product.query.filter(
            Product.name.ilike(f"%{data}%") # type: ignore
        ).first()
    