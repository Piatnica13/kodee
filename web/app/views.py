from flask_admin.contrib.sqla import ModelView
from flask import redirect, url_for
from web.app.security import is_admin
from flask_wtf import FlaskForm
from web.app.validation import product_value, text, email as valid_email, STOCK_FIELDS
from flask_admin import AdminIndexView
from db.models import Product, Product_image, Sale, db
from slugify import slugify
from web.app.log import log_action



class MyAdminPanel(AdminIndexView):
    def is_accessible(self): # type: ignore
        return is_admin()

    def inaccessible_callback(self, name, **kwargs):
        return redirect(url_for('web.index'))


class AdminForm(FlaskForm):
    def __init__(self, *args, obj=None, **kwargs):
        # Flask-Admin unique validators must know the object being edited.
        self._obj = obj
        super().__init__(*args, obj=obj, **kwargs)


class SecurityAdmin(ModelView):
    form_base_class = AdminForm
    def is_accessible(self):
        return is_admin()

    def inaccessible_callback(self, name, **kwargs):
        return redirect(url_for('web.index'))

    def after_model_change(self, form, model, is_created):
        log_action('admin.created' if is_created else 'admin.updated',
                   entity=type(model).__name__, entity_id=model.id)

    def after_model_delete(self, model):
        log_action('admin.deleted', entity=type(model).__name__, entity_id=model.id)


class PersonAdmin(SecurityAdmin):
    column_list = ['id', 'telegram_id', 'name', 'phone', 'email', 'address', 'favourites', 'basket']
    column_searchable_list = ['name', 'phone', 'email']
    form_excluded_columns = ['password', 'is_google', 'google_sub']
    def on_model_change(self, form, model, is_created):
        model.email = valid_email(model.email) if model.email and model.email.strip() else None
        model.name = text(model.name or '', 'Имя', 25, False)
        model.last_name = text(model.last_name or '', 'Фамилия', 40, False)
        if model.telegram_id is not None and not 0 < model.telegram_id < 2**63:
            raise ValueError('Некорректный Telegram ID')
        if model.role not in {'seller', 'worker'} or model.material not in STOCK_FIELDS:
            raise ValueError('Недопустимая роль или материал')

    can_delete = True
    can_edit = True


class ProductAdmin(SecurityAdmin):
    column_list = ['id', 'name', 'price', 'weight', 'concept', 'category', 'descriptions', 'slug', 'images']
    column_searchable_list = ['name']
    can_delete = True
    can_edit = True
    can_create = True

    def on_model_delete(self, model):
        Sale.query.filter_by(product_id=model.id).update({'product_id': None})

    def on_model_change(self, form, model, is_created):
        for field in ('name', 'short_name', 'price', 'price_chet', 'weight', 'concept', 'category', 'descriptions', 'G'):
            setattr(model, field, product_value(field, getattr(model, field)))
        if is_created:
            model.slug = slugify(model.name)
            if not model.slug:
                raise ValueError('Укажите название товара')
        # Image records are created when actual files are uploaded.


class ImagesAdmin(SecurityAdmin):
    def on_model_change(self, form, model, is_created):
        product_id = model.product.id if model.product is not None else model.product_id
        product = Product.query.filter_by(id=product_id).with_for_update().first()
        if product is not None:
            model.product_id = product.id
        if not product or model.num not in range(1, 5):
            raise ValueError('Укажите товар и номер изображения от 1 до 4')
        expected = f'/static/image/productImgs/{product.slug}/img{model.num}.webp'
        if model.img1 != expected:
            raise ValueError('Путь должен соответствовать товару и номеру изображения')
        duplicate = Product_image.query.filter_by(product_id=model.product_id, num=model.num).first()
        if duplicate and duplicate.id != model.id:
            raise ValueError('Изображение с таким номером уже существует')

    column_list = ['id', 'num', 'product_id', 'img1']
    column_searchable_list = ['id', 'product_id']
    can_delete = True
    can_edit = True
    can_create = True

