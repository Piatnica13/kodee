from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import relationship, object_session
from sqlalchemy import JSON
from sqlalchemy.types import BigInteger, Date

from datetime import datetime, timezone


db = SQLAlchemy()


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    telegram_id = db.Column(BigInteger, nullable=True, default=None)

    name = db.Column(db.String(25), nullable=True, default="")
    last_name = db.Column(db.String(40), nullable=True, default="")
    user_name = db.Column(db.String, nullable=True, default="")
    first_name = db.Column(db.String, nullable=True, default="")

    password = db.Column(db.String(255), nullable=True)
    phone = db.Column(db.String(11), nullable=True, default="")
    email = db.Column(db.String(75))

    address = db.Column(db.String(50), nullable=True, default="")
    addresses = db.relationship('Address', backref='person', lazy=True, cascade="all, delete")

    favourites = db.Column(JSON, default=[])
    basket = db.Column(JSON, default=[])

    role = db.Column(db.String, default="seller")
    material = db.Column(db.String, default="gold")
    is_google = db.Column(db.Boolean(), default=False)


    def __init__(self, telegram_id=None, name='', last_name='', user_name='', first_name='', password='', phone='', email='', address='', material="gold", role="seller"):
        self.telegram_id = telegram_id
        self.name = name
        self.last_name = last_name
        self.user_name = user_name
        self.first_name = first_name
        self.password = password
        self.phone = phone
        self.email = email
        self.address = address
        self.material = material
        self.role = role



    def __repr__(self):
        return f"{self.name}"


class Address(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    person_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    name = db.Column(db.String(40), nullable=False)
    city = db.Column(db.String(20), nullable=False)
    street = db.Column(db.String(20), nullable=False)
    home = db.Column(db.String(20), nullable=False)
    flat = db.Column(db.String(20), nullable=True)

    def __repr__(self):
        return f"<Address {self.name}, {self.city}, {self.street}>"


class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    price = db.Column(db.Integer)
    price_chet = db.Column(db.Integer)
    weight = db.Column(db.Float)
    concept = db.Column(db.String(50))
    category = db.Column(db.String(50))
    descriptions = db.Column(db.String(510))

    gold = db.Column(db.Integer, default=0)
    silver = db.Column(db.Integer, default=0)
    form_gold = db.Column(db.Integer, default=0)
    form_silver = db.Column(db.Integer, default=0)

    G = db.Column(db.Integer)
    active = db.Column(db.Boolean(), default=True)
    slug = db.Column(db.String(100), unique=True)
    images = relationship("Product_image", backref="product", lazy=True, cascade="all, delete-orphan")

    
    def image(self):
        """Возвращает путь к первому изображению (где num=1) или стандартное"""
        first_image = (
            object_session(self)
            .query(Product_image) # type: ignore
            .filter_by(product_id=self.id, num=1)
            .first()
        )
        return first_image.img1 if first_image else "/static/image/defaultt.jpg"
    
    def __init__(self, name, price, weight, concept, category,  descriptions, slug, G = 0, gold = 0, silver = 0, form_gold = 0, form_silver = 0, price_chet = 0):
        self.name = name
        self.price = price
        self.price_chet = price_chet
        self.weight = weight
        self.concept = concept
        self.category = category
        self.gold = gold
        self.form_gold = form_gold
        self.silver = silver
        self.form_silver = form_silver
        self.descriptions = descriptions
        self.slug = slug
        self.G = G

    def __repr__(self):
        return f"<{self.slug}>"

class Product_image(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    num = db.Column(db.Integer)
    product_id = db.Column(db.Integer, db.ForeignKey("product.id"), nullable=False)
    img1 = db.Column(db.String(255), nullable=False)
    
    def __init__(self, num, product_id, img1):
        self.num = num
        self.product_id = product_id
        self.img1 = img1
    
    def __repr__(self):
        return f"<Image {self.product_id}>"



class Sale(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    product_id = db.Column(db.Integer, db.ForeignKey("product.id"), nullable=True)
    exclusive_id = db.Column(db.Integer, db.ForeignKey("exclusive.id"), nullable=True)

    name = db.Column(db.String, nullable=False)
    price = db.Column(db.Integer, nullable=False)
    price_chet = db.Column(db.Integer, nullable=False)

    quantity = db.Column(db.Integer, nullable=False, default=1)
    material = db.Column(db.String, nullable=True)

    sold_at = db.Column(Date, nullable=False, default=lambda: datetime.now(timezone.utc).date())



    def __init__(self, product_id, exclusive_id, name, price, price_chet, quantity, material):
        self.product_id = product_id
        self.exclusive_id = exclusive_id
        self.name = name
        self.price = price
        self.price_chet = price_chet
        self.quantity = quantity
        self.material = material


class Exclusive(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    name = db.Column(db.String, nullable=False)
    price = db.Column(db.Integer, nullable=False)
    price_chet = db.Column(db.Integer, nullable=False)
    descriptions = db.Column(db.String, nullable=False)

    created_at = db.Column(Date, nullable=False, default=lambda: datetime.now(timezone.utc).date())


    def __init__(self, name, price, price_chet, descriptions):
        self.name = name
        self.price = price
        self.price_chet = price_chet
        self.descriptions = descriptions


class Certificate(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    amount = db.Column(db.Integer, nullable=False)
    created_at = db.Column(Date, nullable=False, default=lambda: datetime.now(timezone.utc).date())
    user_at = db.Column(Date, nullable=True)


    def __init__(self, amount):
        self.amount = amount