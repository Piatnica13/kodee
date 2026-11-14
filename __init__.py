import os
from urllib.parse import urlsplit
from flask import Flask
from flask_wtf import CSRFProtect
from flask_cors import CORS
from db.models import db
from config import Config, load_environment
from web.app.log import setup_logging
from web.app.admin import admin
from web.app.headers import init_headers
from web.app.proxy import init_proxy
from web.app.oauth import init_oauth


def env_bool(name, default):
    value = os.getenv(name)
    if value is None:
        return default
    if value.lower() not in {'true', 'false', '1', '0'}:
        raise ValueError(f'{name}: допустимы true/false или 1/0')
    return value.lower() in {'true', '1'}


def create_app(test_config=None):
    if test_config is None:
        load_environment()
    app = Flask(__name__, template_folder='web/templates', static_folder='web/static')
    app.config.from_object(Config)
    base = os.getenv('APP_BASE_URL') or os.getenv('RENDER_EXTERNAL_URL') or 'https://kodee.kz'
    # Render terminates public HTTPS at its ingress and forwards HTTP to the app.
    # Use its platform-provided external URL as the default, while allowing an
    # explicit PUBLIC_HTTPS setting for other deployments.
    render_url = os.getenv('RENDER_EXTERNAL_URL', '')
    render_https = urlsplit(render_url).scheme == 'https' and bool(urlsplit(render_url).hostname)
    database_url = os.getenv('DATABASE_URL')
    if database_url and database_url.startswith('postgres://'):
        database_url = 'postgresql://' + database_url[len('postgres://'):]
    app.config.update(
        SECRET_KEY=os.getenv('SECRET_KEY'),
        SQLALCHEMY_DATABASE_URI=database_url,
        ADMIN_EMAIL=os.getenv('ADMIN_EMAIL', ''),
        ADMIN_PASSWORD=os.getenv('ADMIN_PASSWORD', ''),
        LOG_DIR=os.getenv('LOG_DIR', 'logs'),
        PRODUCT_IMAGES_DIR=os.getenv('PRODUCT_IMAGES_DIR') or None,
        PUBLIC_HTTPS=env_bool('PUBLIC_HTTPS', render_https),
        APP_BASE_URL=base,
        SESSION_COOKIE_SECURE=env_bool('SESSION_COOKIE_SECURE', urlsplit(base).scheme == 'https'),
        TRUSTED_HOSTS=[value.strip() for value in os.getenv('TRUSTED_HOSTS', '').split(',') if value.strip()],
        TRUSTED_PROXY_CIDRS=[value.strip() for value in os.getenv('TRUSTED_PROXY_CIDRS', '').split(',') if value.strip()],
        GOOGLE_CLIENT_ID=os.getenv('GOOGLE_CLIENT_ID', ''),
        GOOGLE_CLIENT_SECRET=os.getenv('GOOGLE_CLIENT_SECRET', ''),
        BOT_TOKEN=os.getenv('BOT_TOKEN'),
        CUSTOMER_BOT_TOKEN=os.getenv('CUSTOMER_BOT_TOKEN', ''),
        CUSTOMER_BOT_WEBHOOK_SECRET=os.getenv('CUSTOMER_BOT_WEBHOOK_SECRET', ''),
        CUSTOMER_BOT_ADMIN_IDS={int(value.strip()) for value in os.getenv('CUSTOMER_BOT_ADMIN_IDS', '').split(',') if value.strip()},
        BOT_WEBHOOK_SECRET=os.getenv('BOT_WEBHOOK_SECRET', ''),
        WEBHOOK_URL=os.getenv('WEBHOOK_URL', ''),
        BOT_ALLOWED_USER_IDS={int(value.strip()) for value in os.getenv('BOT_ALLOWED_USER_IDS', '').split(',') if value.strip()},
    )
    for name in ('X_FOR', 'X_PROTO', 'X_HOST', 'X_PORT'):
        app.config['PROXY_' + name] = int(os.getenv('PROXY_' + name, '0'))
    if test_config is not None:
        app.config.update(test_config)
    if not app.secret_key or not app.config.get('SQLALCHEMY_DATABASE_URI'):
        raise RuntimeError('Задайте SECRET_KEY и DATABASE_URL')
    setup_logging(app)
    init_headers(app)
    init_proxy(app)
    db.init_app(app)
    admin.init_app(app)
    init_oauth(app)
    from web.app.routes import web_api
    from bot.api.api import bot_api
    app.register_blueprint(web_api)
    app.register_blueprint(bot_api)
    from customer_bot import init_customer_bot, customer_api, register_commands as register_customer_commands
    init_customer_bot(app)
    csrf = CSRFProtect(app)
    csrf.exempt(bot_api)
    csrf.exempt(customer_api)
    CORS(app, origins=[app.config['APP_BASE_URL']], supports_credentials=True,
         methods=['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS'],
         allow_headers=['Content-Type', 'Authorization', 'X-CSRFToken'])
    from bot.bot.bot import start_bot
    from db.maintenance import register_commands
    start_bot(app)
    register_commands(app)
    register_customer_commands(app)
    return app
