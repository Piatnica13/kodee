import hmac
from flask import request, Blueprint, current_app, abort
from telebot import types

bot_api = Blueprint('bot', __name__, url_prefix='/bot')


@bot_api.route('/webhook', methods=['POST'])
def webhook():
    secret = current_app.config.get('BOT_WEBHOOK_SECRET', '')
    bot = current_app.extensions.get('telegram_bot')
    if not bot or len(secret) < 32:
        abort(503)
    supplied = request.headers.get('X-Telegram-Bot-Api-Secret-Token', '')
    if not hmac.compare_digest(secret.encode(), supplied.encode()):
        abort(403)
    if not request.is_json or request.content_length is None or request.content_length > 1024 * 1024:
        abort(400)
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or type(data.get('update_id')) is not int or not any(key in data for key in ('message', 'callback_query')):
        abort(400)
    try:
        update = types.Update.de_json(data)
        event = update.callback_query or update.message
        message = event.message if update.callback_query else event
        if not message or not message.chat or not event.from_user:
            abort(400)
    except (ValueError, TypeError, KeyError, AttributeError):
        abort(400)
    try:
        bot.process_new_updates([update])
    except Exception:
        current_app.logger.exception('Ошибка обработки Telegram update')
        abort(500)
    return 'OK', 200
