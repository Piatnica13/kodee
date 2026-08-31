from db.models import db
from __init__ import create_app, create_oauth
from web.app.services.user import UserService
from db.add_products import allProducts

from bot.bot.bot import start_bot

import os


# Создание flask приложения
app = create_app()
app.logger.info("Flask-приложение создано.")

start_bot(app)


# OAuth google
oauth = create_oauth(app)

# Создание всех таблиц и добавление админа
with app.app_context():
    db.create_all()
    
    # СОЗДАЕМ АДМИН АККАУНТ
    UserService.add_admin()
    allProducts(db, app)
    
if __name__ == '__main__':
    port = int(os.getenv("PORT", 5000))
    app.run(port=port, host="0.0.0.0")