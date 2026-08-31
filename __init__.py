from flask import Flask
from dotenv import load_dotenv
from db.models import db
from config import Config
from web.app.log import setup_logging
from web.app.admin import admin
from flask_wtf import CSRFProtect
from flask_cors import CORS
from authlib.integrations.flask_client import OAuth
from werkzeug.middleware.proxy_fix import ProxyFix
import os

def create_app():
    app = Flask(__name__, template_folder="web/templates", static_folder="web/static")
    

    app.wsgi_app = ProxyFix(
        app.wsgi_app,
        x_for=1,
        x_proto=1,
        x_host=1
    )

    
    # Логи (log.py)
    setup_logging(app)
    app.logger.info("Логирование настроено.")


    # Подключение .env файла
    load_dotenv('.password.env')
    app.logger.info("Файл .env загружен.")


    # Подключение правил
    app.config.from_object(Config)


    # Подключение базы данных
    app.config['SQLALCHEMY_DATABASE_URI'] =  os.getenv("DATABASE_URL")
        
    # Инициализация соединения
    db.init_app(app) 
    app.logger.info("База данных инициализирована.")
    
    
    app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
        'pool_pre_ping': True
    }

    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.logger.info("Настройки базы данных заданы (POSTGRES).")


    # Создание ключа
    app.secret_key = os.getenv("SECRET_KEY")
    app.logger.info(f"Секретный ключ загружен из .env.")


    # Инициализация админ панели
    admin.init_app(app)
    app.logger.info("Админ панель инициализирована.")
    

    # Cookie Безопасность
    app.config.update(
        SESSION_COOKIE_SECURE=True,      # Только через HTTPS
        SESSION_COOKIE_HTTPONLY=True,    # JS не получит доступ к cookie
        SESSION_COOKIE_SAMESITE='Lax'    # Защита от CSRF
    )
    app.logger.info("Cookie настроено")

    # Регистрация блюпринтов
    from web.app.routes import web_api
    from bot.api.api import bot_api

    app.register_blueprint(web_api)
    app.register_blueprint(bot_api)


    # CSRF Безопасность
    csrf = CSRFProtect(app)
    csrf.exempt(bot_api)
    app.logger.info("CSRF настроено")

    
    # IOS Безопасность
    CORS(app, 
        origins=["https://kodee.kz"],
        supports_credentials=True,
        methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization"])
    return app


def create_oauth(app):
    # OAuth google
    oauth = OAuth(app)
    app.logger.info("OAuth создано")

    # Настройка OAuth google
    oauth.register(
        name='google',
        client_id=os.getenv("GOOGLE_CLIENT_ID"),
        client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
        server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
        client_kwargs={'scope': 'openid email profile'}
    )
    return oauth