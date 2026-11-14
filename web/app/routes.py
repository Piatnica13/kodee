from flask import Blueprint, current_app,  render_template, request, redirect, session, flash, jsonify, send_from_directory, current_app, url_for
from functools import wraps
from db.models import db, Product
from web.app.forms import LoginForm, RegisterForm, ProfilMainPassForm, ProfilSplitForm, ProfilAddSplit, ProfilAddressForm
from web.app.services.user import UserService
from web.app.services.product import ProductService
from web.app.services.application import AppService
from web.app.security import is_admin, current_user
from web.app.log import log_action
from werkzeug.exceptions import HTTPException
from sqlalchemy.exc import IntegrityError
import os

web_api = Blueprint("web", __name__)

# ИДЕНТИФИКАЦИЯ USER
def login_required(f):
    @wraps(f)
    def decorater(*args, **kwargs):
        user = UserService.get_user(session.get("user_id")) # type: ignore
        if not user:
            session.pop('user_id', None)
            session.pop('admin', None)
            if request.is_json:
                return jsonify(success=False, error='Для этого действия войдите в аккаунт'), 401
            return redirect('/login')
        return f(user=user, *args, **kwargs)
    return decorater

# ПРОВЕРКА НА АДМИН ДОСТУП
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not is_admin():
            current_app.logger.warning("Попытка доступа к админке без прав.")
            return redirect('/')
        return f(*args, **kwargs)
    return decorated_function


def json_payload():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        from flask import abort
        abort(400, description='Ожидается JSON-объект')
    return data


@web_api.app_errorhandler(ValueError)
def validation_error(error):
    db.session.rollback()
    if request.is_json or request.endpoint == 'web.add_imgs':
        return jsonify(success=False, error=str(error)), 400
    flash(str(error))
    return redirect('/profil' if session.get('user_id') else '/register')


@web_api.app_errorhandler(IntegrityError)
def integrity_error(error):
    db.session.rollback()
    current_app.logger.warning('Нарушение ограничения целостности данных')
    if request.is_json or request.endpoint == 'web.add_imgs':
        return jsonify(success=False, error='Данные конфликтуют с существующей записью'), 409
    flash('Проверьте данные: запись конфликтует с существующей')
    return redirect('/profil')


@web_api.app_errorhandler(HTTPException)
def http_error(error):
    if request.is_json or request.path.startswith('/api/') or request.endpoint == 'web.add_imgs':
        return jsonify(success=False, error=error.description), error.code
    return render_template('error.html', code=error.code, title=error.description), error.code


@web_api.route('/healthz')
def healthz():
    # Process liveness only: safe before an explicit first schema migration.
    return jsonify(status='ok')


@web_api.route('/static/image/productImgs/<slug>/<filename>')
def product_image_file(slug, filename):
    from pathlib import Path
    from flask import abort
    from web.app.images import image_directory
    if filename not in {'img1.webp','img2.webp','img3.webp','img4.webp'}:
        abort(404)
    try:
        uploaded = image_directory(slug)
    except ValueError:
        abort(404)
    if (uploaded / filename).is_file():
        return send_from_directory(uploaded, filename)
    bundled = Path(current_app.static_folder) / 'image' / 'productImgs' / slug
    return send_from_directory(bundled, filename)


# Главный маршрут
@web_api.route('/')
def index():
    products = {p.slug: p for p in Product.query.filter_by(active=True).all()}
    admin = is_admin()
    if admin:
        return render_template('index.html', admin=True, products=products)
    return render_template('index.html', admin=False, products=products)


# ПРОФИЛЬ
@web_api.route('/profil', methods=["GET"])
@login_required
def profil(user):
    formSplit = ProfilSplitForm()
    formPass = ProfilMainPassForm()
    formAdd = ProfilAddSplit()
    formAddress = ProfilAddressForm()

    favorite_products = Product.query.filter(Product.id.in_(user.favourites or []), Product.active.is_(True)).all()

    return render_template("profil.html", user=user, favorite_products=favorite_products, formSplit=formSplit, formPass=formPass, formAdd=formAdd, formAddress=formAddress)

@web_api.route('/profil/update_password', methods=["POST"])
@login_required
def update_password(user):
    data = request.form

    UserService.update_password(user, data)

    db.session.commit()
    log_action('profile.password_changed')

    return redirect("/profil")


@web_api.route('/profil/update_user', methods=["POST"])
@login_required
def update_user(user):
    data = request.form

    UserService.update_user(user, data)

    db.session.commit()
    log_action('profile.updated')

    return redirect("/profil")

@web_api.route('/profil/change_address', methods=["POST"])
@login_required
def change_address(user):
    data = request.form

    UserService.change_address(user, data)

    db.session.commit()
    log_action('profile.addresses_updated')

    flash("Адреса успешно обновлены.")

    return redirect("/profil")

@web_api.route('/profil/add_address', methods=["POST"])
@login_required
def profil_add_address(user):
    form = ProfilAddSplit()

    if not form.validate_on_submit():
        flash("Обязательные поля не были заполнены. Повторите попытку.")
        return redirect("/profil")

    data = request.form

    UserService.add_address(user, data)

    db.session.commit()
    log_action('address.added')

    flash("Адрес успешно добавлен.")

    return redirect("/profil")

# КОРЗИНА
# Маршрут для корзины
@web_api.route('/basket', methods=["GET", "POST"])
@login_required
def basket(user):
    form = ProfilAddSplit()
    basket = ProductService.get_user_basket(user)

    return render_template('basket.html', basket=basket, user=user, form=form)

# Добавление товара в корзину
@web_api.route('/add_basket', methods=['POST'])
def add_basket():
    data = json_payload()
    result = ProductService.add_product_to_basket(data)
    log_action('basket.added', outcome='success' if result.get('success') else 'failure', product_id=data.get('product_id') if type(data.get('product_id')) is int else None)

    return jsonify(result)

# Удаление товара из корзины
@web_api.route('/delete_basket', methods=['POST'])
@login_required
def delete_basket(user):
    data = json_payload()
    result = ProductService.delete_product_from_basket(user, data)
    log_action('basket.removed', outcome='success' if result.get('success') else 'failure', product_id=data.get('product_id') if type(data.get('product_id')) is int else None)

    return jsonify(result)

# ДОБАВЛЕНИЕ АДРЕСА
@web_api.route('/add_address', methods=["POST"])
@login_required
def addAddress(user):
    data = json_payload()
    result = UserService.add_address(user, data)
    log_action('address.added')

    return jsonify(result)


# ДОБАВЛЕНИЕ ИЛИ УДАЛЕНИЕ ИЗБРАННОГО
@web_api.route('/add_favorite', methods=['POST'])
def add_favorite():
    data = json_payload()

    result = ProductService.add_or_delete_favorite_product(data)
    log_action('favorite.toggled', outcome='success' if result.get('success') else 'failure', product_id=data.get('product_id') if type(data.get('product_id')) is int else None)

    return jsonify(result)


# ПЕРЕДАЧА ВСЕХ ТОВАРОВ В JS
@web_api.route("/AllProductJS")
def AllProductJS():
    result = ProductService.trans_products_to_JS()
    return jsonify(result)


# ПОИСК
@web_api.route("/search")
def search():
    data = request.args
    result = ProductService.search_product(data)
    return jsonify(result)


# МАГАЗИН
@web_api.route('/shop')
def shop():
    result = ProductService.get_products_for_properties()
    return render_template("shop.html", products_json=result)


# КОНТАКТЫ
@web_api.route('/contact')
def contact():
    current_app.logger.debug("Открыта страница контактов.")
    return render_template('contact.html')


# СПРАВКА
@web_api.route('/help/<theme>')
def help(theme):
    current_app.logger.debug("Открыта страница справки.")
    return render_template('help.html', theme=theme)


# ИНДИВИДУАЛЬНЫЙ ЗАКАЗ
@web_api.route('/individual')
def individual_order():
    current_app.logger.debug("Открыта страница индивидуального заказа.")
    return render_template('individual.html')


# РЕГИСТРАЦИЯ
@web_api.route('/register')
def register():
    form = RegisterForm()
    current_app.logger.debug("Открыта страница регистрации.")
    return render_template('register.html', form=form)

@web_api.route("/register/add_user", methods=['POST'])
def reg_user():
    result = UserService.add_user()
    log_action('registration', outcome='success' if result['success'] else 'failure')

    if result["success"] == False:
        flash(result["message"])
        return redirect("/register")

    flash(result["message"])
    return redirect("/")


# ВХОД В АККАУНТ
@web_api.route('/login')
def login():
    form = LoginForm()
    current_app.logger.debug("Открыта страница входа.")
    return render_template('login.html', form=form)

@web_api.route('/login/log_user', methods=['POST'])
def log_user():
    admin_email = current_app.config.get("ADMIN_EMAIL")
    admin_password = current_app.config.get("ADMIN_PASSWORD")
    result = UserService.log_user(admin_email, admin_password)
    log_action('login', outcome='success' if result['success'] else 'failure', method='password')
    if result['success'] == False:
        flash(result["message"])
        return redirect('/login')

    if result['admin']:
        flash(result["message"])
        return redirect('/admin')

    flash(result["message"])
    return redirect('/')


# ВХОД С ПОМОЩЬЮ GOOGLE
@web_api.route('/login/google')
def google_login():
    from web.app.oauth import start_google_flow
    try:
        return start_google_flow()
    except HTTPException:
        raise
    except Exception:
        current_app.logger.exception('Не удалось начать Google OAuth')
        flash('Вход через Google временно недоступен')
        return redirect('/login')


@web_api.route('/profil/google/link', methods=['POST'])
@login_required
def link_google(user):
    from web.app.oauth import start_google_flow
    try:
        return start_google_flow(link=True)
    except HTTPException:
        raise
    except Exception:
        current_app.logger.exception('Не удалось начать привязку Google')
        flash('Привязка Google временно недоступна')
        return redirect('/profil')


# ВХОД С ПОМОЩЬЮ GOOGLE
@web_api.route('/callback')
def authorize():
    linking = bool(session.get('google_flow', {}).get('link_user_id'))
    result = UserService.log_user_from_google()
    log_action('google.link' if linking else 'login', outcome='success' if result['success'] else 'failure', method='google')

    if result['success'] == False:
        flash(result['message'])
        return redirect('/login')

    flash(result['message'])
    return redirect('/profil' if linking else '/')


# ВЫХОД ИЗ АККАУНТА
@web_api.route('/logout')
def logout():
    if session.get('user_id') is not None:
        log_action('logout')
    session.pop('user_id', None)
    session.pop('admin', None)

    flash("Вы успешно вышли из аккаунта!")

    return redirect('/')
#

@web_api.route('/admin/panel')
@admin_required
def admin_panel():
    return render_template('admin.html')

# Добавление изображений в созданную папку, админ
@web_api.route('/admin/add_imgs', methods=['POST'])
@admin_required
def add_imgs():
    data_files = request.files
    data_form = request.form
    result = ProductService.add_imgs_for_product(data_files, data_form)
    log_action('product.images_updated')

    return jsonify(result)

# СТРАНИЦА ПРОДУКТА
@web_api.route('/product/<slug>')
def product(slug):
    result = ProductService.check_user_for_product_page(slug)

    return render_template('product.html', product=result['product'], user=result['user'], address=result['address'], favarite=result['favorite'])


# ВЫВОД ПРОДУКТОВ
@web_api.route('/api/products')
def get_product():
    result = ProductService.get_product()
    return jsonify(result)


# ВСЕ СЕРВЕРНЫЕ МОМЕНТЫ
@web_api.after_app_request
def apply_security_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    if request.is_secure:
        response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    response.headers['X-Frame-Options'] = 'DENY'
    return response

@web_api.route('/.well-known/security.txt')
def security_txt():
    return send_from_directory(current_app.static_folder + "/.well-known", 'security.txt') # type: ignore

@web_api.route('/robots.txt')
def robots():
    return send_from_directory(current_app.static_folder, 'robots.txt') # type: ignore

@web_api.route('/sitemap.xml')
def sitemap():
    return send_from_directory(current_app.static_folder, 'sitemap.xml') # type: ignore

# ОБРАБОТКА ОШИБОК
# @web_api.app_errorhandler(Exception)
# def errors(error):
#     result = AppService.show_error(error)
#     return render_template("error.html", code=result['code'], title=result['title'])
