from flask import request, Blueprint
from telebot import types
from dotenv import load_dotenv
import bot.bot.bot as bot
import os


load_dotenv(".env")

bot_api = Blueprint("bot", __name__, url_prefix="/bot")


@bot_api.route('/webhook', methods=['POST'])
def webhook():
    json_str = request.get_data().decode('utf-8')
    update = types.Update.de_json(json_str)
    bot.bot.process_new_updates([update]) # type: ignore
        
    return "OK", 200


@bot_api.route('/setwebhook')
def set_webhook():
    bot.bot.remove_webhook()
    bot.bot.set_webhook(os.getenv("WEBHOOK_URL"))
    return "Webhook set", 200