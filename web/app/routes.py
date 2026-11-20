from flask import Blueprint, current_app, render_template, request, redirect, session, flash, jsonify, send_from_directory, url_for, Response, abort
from xml.etree import ElementTree as ET
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
import re
import time

from web.app.privacy import CONSENT_VERSION

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


# Названия в БД и URL остаются неизменными. Незнакомые категории
# показываем как есть, не пытаясь автоматически склонять их.
CATEGORY_LABELS = {'Кулон': 'Кулоны', 'Бегунок': 'Бегунки',
                   'Монеточка': 'Монеточки', 'Колье': 'Колье'}
CATEGORY_CONTENT = {
    'Монеточка': {
        'heading': 'Монетки для гравировки',
        'title': 'Монетки с гравировкой — одна и две стороны | KoDee Desire',
        'description': 'Монетки KoDee Desire для личной гравировки: имя, дата или рисунок. Сравните варианты с одной и двумя сторонами, фотографии, вес и цены.',
        'intro': 'Имя, дата, несколько слов или рисунок — то, что хочется оставить рядом. Здесь два варианта монеток: гравировка с одной или двух сторон.',
    },
    'Бегунок': {
        'heading': 'Бегунки на нити',
        'title': 'Бегунки на нити — мини и стандартный | KoDee Desire',
        'description': 'Бегунки KoDee Desire на нити: мини и стандартный. Две модели с фотографиями, весом и ценой.',
        'intro': 'Бегунок мини и бегунок — два размера одной лаконичной детали. На фотографиях оба показаны на нити.',
    },
}


@web_api.app_context_processor
def category_labels():
    from web.app.seo import (engraving_summary, product_title, product_meta_description,
                             product_display_name, product_description, product_photo_alt,
                             product_gallery_images, format_price)
    return {'category_label': lambda value: CATEGORY_LABELS.get(value, value),
            'engraving_summary': engraving_summary, 'product_display_name': product_display_name,
            'product_description': product_description, 'product_photo_alt': product_photo_alt,
            'product_gallery_images': product_gallery_images,
            'product_title': product_title, 'product_meta_description': product_meta_description,
            'format_price': format_price}


# МАГАЗИН
@web_api.route('/shop')
def shop():
    products = Product.query.filter_by(active=True).order_by(Product.id).all()
    grouped = {category: [p for p in products if p.category == category]
               for category in ('Кулон', 'Монеточка', 'Бегунок')}
    return render_template("shop.html", products=products, grouped=grouped)


@web_api.route('/category/<category>')
def category(category):
    if category == 'Кулон':
        return redirect(url_for('web.thread_bracelets'), code=301)
    products = Product.query.filter_by(active=True, category=category).order_by(Product.id).all()
    if not products:
        abort(404)
    return render_template('category.html', category=category, products=products,
                           category_content=CATEGORY_CONTENT.get(category, {}),
                           catalogue_categories={row[0] for row in db.session.query(Product.category).filter_by(active=True).distinct()})


@web_api.route('/braslety-na-niti')
def thread_bracelets():
    products = Product.query.filter_by(active=True, category='Кулон').order_by(Product.id).all()
    featured = {p.slug: p for p in products if p.slug in {'samolet', 'klever', 'derevo', 'korona'}}
    return render_template('category.html', category='Кулон', products=products, featured=featured,
        catalogue_categories={row[0] for row in db.session.query(Product.category).filter_by(active=True).distinct()},
        category_content={
            'heading': 'Кулоны желаний на нити',
            'title': 'Кулоны желаний на нити — коллекция KoDee Desire',
            'description': 'Кулоны желаний KoDee Desire на нити: Самолёт, Клевер, Солнце и другие символы. Фотографии моделей, вес и цены. Мастерская в Караганде.',
            'intro': 'У каждого желания свой знак. Нить оставляет символ рядом каждый день.',
        })


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
    from db.engraving_examples import ENGRAVING_EXAMPLES
    coins = Product.query.filter_by(active=True, category='Монеточка').order_by(Product.id).all()
    return render_template('individual.html', coins=coins, engraving_examples=ENGRAVING_EXAMPLES)


# РЕГИСТРАЦИЯ
@web_api.app_context_processor
def privacy_context():
    return {'privacy_consent_version': CONSENT_VERSION}


@web_api.route('/privacy')
def privacy():
    return render_template('privacy.html')


@web_api.route('/register')
def register():
    form = RegisterForm()
    current_app.logger.debug("Открыта страница регистрации.")
    return render_template('register.html', form=form, return_to=product_return_path(request.args.get('next', '')))

@web_api.route("/register/add_user", methods=['POST'])
def reg_user():
    result = UserService.add_user()
    log_action('registration', outcome='success' if result['success'] else 'failure')

    if result["success"] == False:
        return_to = product_return_path(request.form.get('next'))
        return render_template('register.html', form=RegisterForm(), return_to=return_to,
                               registration_error=result['message'],
                               consent_checked=request.form.get('privacy_consent') == CONSENT_VERSION,
                               entered_name=request.form.get('name', ''),
                               entered_email=request.form.get('email', '')), 400

    flash(result["message"])
    return redirect(product_return_path(request.form.get('next')) or '/')


# ВХОД В АККАУНТ
def product_return_path(value):
    """Allow return only to a local catalogue product, never an arbitrary URL."""
    return value if isinstance(value, str) and re.fullmatch(r'/product/[a-z0-9-]+', value) else ''


@web_api.route('/login')
def login():
    form = LoginForm()
    current_app.logger.debug("Открыта страница входа.")
    return_to = product_return_path(request.args.get('next', ''))
    return render_template('login.html', form=form, return_to=return_to)

@web_api.route('/login/log_user', methods=['POST'])
def log_user():
    admin_email = current_app.config.get("ADMIN_EMAIL")
    admin_password = current_app.config.get("ADMIN_PASSWORD")
    result = UserService.log_user(admin_email, admin_password)
    log_action('login', outcome='success' if result['success'] else 'failure', method='password')
    if result['success'] == False:
        flash(result["message"])
        return_to = product_return_path(request.form.get('next'))
        return redirect(url_for('web.login', next=return_to)) if return_to else redirect('/login')

    if result['admin']:
        flash(result["message"])
        return redirect('/admin')

    flash(result["message"])
    return_to = product_return_path(request.form.get('next'))
    if return_to:
        return redirect(return_to)
    return redirect('/')


# ВХОД С ПОМОЩЬЮ GOOGLE
@web_api.route('/login/google')
def google_login():
    from web.app.oauth import start_google_flow
    session.pop('google_signup_pending', None)
    return_to = product_return_path(request.args.get('next', ''))
    try:
        return start_google_flow(return_to=return_to)
    except HTTPException:
        raise
    except Exception:
        current_app.logger.exception('Не удалось начать Google OAuth')
        flash('Вход через Google временно недоступен')
        return redirect(url_for('web.login', next=return_to or None))


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
    return_to = product_return_path(session.get('google_flow', {}).get('return_to'))
    result = UserService.log_user_from_google()
    if result.get('needs_consent'):
        session['google_signup_pending'] = {
            'subject': result['subject_marker'], 'return_to': return_to,
            'expires_at': time.time() + current_app.config['OAUTH_FLOW_TTL'],
        }
        return redirect(url_for('web.google_signup_consent'))
    log_action('google.link' if linking else 'login', outcome='success' if result['success'] else 'failure', method='google')

    if result['success'] == False:
        flash(result['message'])
        return redirect(url_for('web.login', next=return_to)) if return_to else redirect('/login')

    flash(result['message'])
    return redirect('/profil' if linking else (return_to or '/'))


@web_api.route('/register/google/consent', methods=['GET', 'POST'])
def google_signup_consent():
    from web.app.oauth import start_google_flow

    pending = session.get('google_signup_pending')
    return_to = product_return_path(pending.get('return_to')) if pending else ''
    if current_user():
        session.pop('google_signup_pending', None)
        return redirect(return_to or '/')
    declined = request.method == 'POST' and request.form.get('decision') == 'decline'
    if not pending or pending['expires_at'] <= time.time() or declined:
        session.pop('google_signup_pending', None)
        return redirect(url_for('web.login', next=return_to or None))
    if request.method == 'GET':
        return render_template('google_signup_consent.html')
    if request.form.get('privacy_consent') != CONSENT_VERSION:
        return render_template('google_signup_consent.html',
                               registration_error='Подтвердите согласие на обработку персональных данных.'), 400
    session.pop('google_signup_pending', None)
    accepted_at = time.time()
    try:
        response = start_google_flow(return_to=pending['return_to'])
        session['google_flow'] = {**session['google_flow'], 'signup_consent': {
            'subject': pending['subject'], 'version': CONSENT_VERSION, 'accepted_at': accepted_at,
        }}
        return response
    except Exception:
        session.pop('google_flow', None)
        current_app.logger.warning('Не удалось продолжить регистрацию через Google')
        flash('Вход через Google временно недоступен')
        return redirect(url_for('web.login', next=pending['return_to']))


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
    from web.app.seo import product_schema
    from db.product_editorial import RELATED_SLUGS
    related_slug = RELATED_SLUGS.get(slug)
    related = Product.query.filter_by(slug=related_slug, active=True).one_or_none() if related_slug else None
    return render_template('product.html', product=result['product'], user=result['user'], address=result['address'], favarite=result['favorite'], product_schema=product_schema(result['product']), related=related)


# ВЫВОД ПРОДУКТОВ
@web_api.route('/api/products')
def get_product():
    result = ProductService.get_product()
    return jsonify(result)


# ВСЕ СЕРВЕРНЫЕ МОМЕНТЫ
@web_api.after_app_request
def apply_security_headers(response):
    if request.endpoint in {'web.authorize', 'web.google_signup_consent'}:
        response.headers['Cache-Control'] = 'no-store'
    if request.endpoint == 'web.privacy' or request.path.startswith(('/login', '/register', '/profil', '/basket', '/admin', '/callback', '/logout')) or (request.endpoint == 'web.help' and request.view_args.get('theme') != 'primary'):
        response.headers['X-Robots-Tag'] = 'noindex, nofollow'
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
    namespace = 'http://www.sitemaps.org/schemas/sitemap/0.9'
    ET.register_namespace('', namespace)
    root = ET.Element(f'{{{namespace}}}urlset')
    paths = [url_for('web.index'), url_for('web.shop'), url_for('web.thread_bracelets'), url_for('web.contact'),
             url_for('web.individual_order'), url_for('web.help', theme='primary')]
    products = Product.query.filter_by(active=True).order_by(Product.slug).all()
    categories = sorted({p.category for p in products
                         if p.category and p.category != 'Кулон' and '/' not in p.category})
    paths.extend(url_for('web.category', category=value) for value in categories)
    paths.extend(url_for('web.product', slug=p.slug) for p in products if p.slug and '/' not in p.slug)
    for path in dict.fromkeys(paths):
        entry = ET.SubElement(root, f'{{{namespace}}}url')
        ET.SubElement(entry, f'{{{namespace}}}loc').text = 'https://kodee.kz' + path
    ET.indent(root)
    return Response(ET.tostring(root, encoding='utf-8', xml_declaration=True) + b'\n',
                    mimetype='application/xml')

# ОБРАБОТКА ОШИБОК
# @web_api.app_errorhandler(Exception)
# def errors(error):
#     result = AppService.show_error(error)
#     return render_template("error.html", code=result['code'], title=result['title'])
