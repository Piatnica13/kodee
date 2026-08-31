from flask_admin import Admin
from db.models import User, Product, Product_image
from db.models import db
from web.app.views import PersonAdmin, ProductAdmin, ImagesAdmin,MyAdminPanel

admin = Admin(
    name="Kodee Desire Panel",
    index_view=MyAdminPanel()
    )

admin.add_view(PersonAdmin(User, db.session))
admin.add_view(ProductAdmin(Product, db.session))
admin.add_view(ImagesAdmin(Product_image, db.session))