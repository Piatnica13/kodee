from telebot import TeleBot
from telebot.types import BotCommand

from bot.services.bot_service import BotService
from bot.services.user_service import UserService
from bot.services.product_service import ProductService
from bot.services.markup_service import MarkupService
from bot.services.notification_service import NotificationService

from bot.services.handlers.callbacks.menu import start_menu

from db.models import db
from ..services.fsm.in_memory_fsm import InMemoryFSMStorage

from dotenv import load_dotenv
import os
import traceback


load_dotenv(".env")
TOKEN = str(os.getenv("BOT_TOKEN"))

bot = TeleBot(TOKEN)

user = UserService()

product_service = ProductService()

fsm = InMemoryFSMStorage()

markup = MarkupService()

notification = NotificationService()


bot.set_my_commands([
    BotCommand("start", "🏠 Главное меню"),
    BotCommand("products", "📦 Список товаров"),
])

def start_bot(app):
    bot_service = BotService(bot=bot, user=user, app=app, fsm=fsm, ps=product_service, db=db, markup=markup, notification=notification)


    @bot.message_handler(commands=['start'])
    def start(msg):
        with app.app_context():
            try:
                    user.reg(msg)
                    start_menu(bot_service.ctx, msg)
            except Exception as e:
                bot.send_message(chat_id=msg.chat.id, text=f"Ошибка start: {e}, {traceback.format_exc()}")


    @bot.callback_query_handler(func=lambda call: True)
    def callbacks(call):
        with app.app_context():
            try:
                bot_service.check_callbacks(call)
            except Exception as e:
                bot.send_message(chat_id=call.message.chat.id, text=f"Ошибка callback: {e}, {traceback.format_exc()}")


    @bot.message_handler(content_types=['text'])
    def send_user_message(msg):
        with app.app_context():
            try:
                bot_service.check_text_msg(msg)
            except Exception as e:
                bot.send_message(chat_id=msg.chat.id, text=f"Ошибка text: {e}, {traceback.format_exc()}")


    @bot.message_handler(content_types=['photo'])
    def send_user_image(msg):
        with app.app_context():
            try:
                bot_service.check_image(msg)
            except Exception as e:
                bot.send_message(chat_id=msg.chat.id, text=f"Ошибка text: {e}, {traceback.format_exc()}")
