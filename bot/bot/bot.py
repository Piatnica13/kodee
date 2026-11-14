from functools import wraps
from flask import g
import re
from telebot import TeleBot
from telebot.types import BotCommand
from bot.services.bot_service import BotService
from bot.services.user_service import UserService
from bot.services.product_service import ProductService
from bot.services.markup_service import MarkupService
from bot.services.notification_service import NotificationService
from bot.services.handlers.callbacks.menu import start_menu
from bot.services.fsm.database_fsm import DatabaseFSMStorage
from bot.services.access import allowed
from db.models import db


def start_bot(app):
    """Register local handlers without contacting Telegram during application import."""
    token = app.config.get('BOT_TOKEN')
    if not token:
        app.extensions['telegram_bot'] = None
        return None
    bot = TeleBot(token, threaded=False)
    service = BotService(bot=bot, user=UserService(), app=app,
        fsm=DatabaseFSMStorage(), ps=ProductService(), db=db,
        markup=MarkupService(), notification=NotificationService())
    app.extensions['telegram_bot'] = bot
    app.extensions['bot_service'] = service

    def protected(callback=False):
        def decorate(handler):
            @wraps(handler)
            def run(event):
                with app.app_context():
                    message = event.message if callback else event
                    actor = event.from_user
                    if not allowed(message, actor):
                        app.logger.warning('Отклонено неразрешённое обращение к боту, user_id=%s', actor.id if actor else None)
                        return
                    g.telegram_actor_id = actor.id
                    try:
                        with service.ctx.fsm.scope(message.chat.id):
                            handler(event)
                    except ValueError as error:
                        db.session.rollback()
                        app.logger.warning('Некорректный ввод бота: %s', error)
                        bot.send_message(message.chat.id, 'Некорректный ввод. Проверьте данные и повторите попытку.')
                    except Exception:
                        db.session.rollback()
                        app.logger.exception('Ошибка обработчика бота, user_id=%s', actor.id)
                        # Internal errors are logged only; no SQL/tracebacks in Telegram.
            return run
        return decorate

    @bot.message_handler(commands=['start', 'products'])
    @protected()
    def start(message):
        service.ctx.users.reg(message)
        start_menu(service.ctx, message)

    @bot.callback_query_handler(func=lambda call: True)
    @protected(callback=True)
    def callbacks(call):
        service.check_callbacks(call)

    @bot.message_handler(content_types=['text'])
    @protected()
    def text(message):
        service.check_text_msg(message)

    @bot.message_handler(content_types=['photo'])
    @protected()
    def photo(message):
        service.check_image(message)

    return bot


def configure_webhook(app):
    bot = app.extensions.get('telegram_bot')
    secret = app.config.get('BOT_WEBHOOK_SECRET', '')
    url = app.config.get('WEBHOOK_URL', '')
    if not bot or not re.fullmatch(r'[A-Za-z0-9_-]{32,256}', secret) or not url.startswith('https://'):
        raise ValueError('Задайте BOT_TOKEN, WEBHOOK_URL (HTTPS) и BOT_WEBHOOK_SECRET (минимум 32 символа)')
    bot.set_my_commands([BotCommand('start', '🏠 Главное меню'), BotCommand('products', '📦 Список товаров')])
    if not bot.set_webhook(url=url, secret_token=secret, allowed_updates=['message', 'callback_query']):
        raise ValueError('Telegram не подтвердил установку webhook')
