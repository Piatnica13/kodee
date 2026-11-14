"""Customer Telegram bot integrated with the main Flask application."""
from dataclasses import dataclass
import hmac
import re
import time

import click
from flask import Blueprint, abort, current_app, request
from sqlalchemy import select, update, func

from db.models import db
from .catalog import Catalog
from .dialog import Dialog
from .storage import Store, orders, outbox
from .telegram import Telegram, TelegramError, configure_bot, deliver, receive


@dataclass(frozen=True)
class Settings:
    public_url: str
    admin_ids: tuple
    delivery_note: str = 'Способ, стоимость и срок доставки согласуем при подтверждении заказа.'


customer_api = Blueprint('customer_bot', __name__, url_prefix='/customer-bot')


def init_customer_bot(app):
    allowed = app.config['BOT_ALLOWED_USER_IDS']
    recipients = app.config['CUSTOMER_BOT_ADMIN_IDS']
    if app.config.get('CUSTOMER_BOT_TOKEN') and app.config['CUSTOMER_BOT_TOKEN'] == app.config.get('BOT_TOKEN'):
        raise ValueError('Для клиентского и административного ботов нужны разные токены')
    if not recipients.issubset(allowed):
        raise ValueError('CUSTOMER_BOT_ADMIN_IDS должны входить в BOT_ALLOWED_USER_IDS')
    store = Store(lambda: db.engine)
    settings = Settings(public_url=app.config['APP_BASE_URL'], admin_ids=tuple(sorted(recipients)))
    app.extensions['customer_bot'] = Dialog(store, Catalog(store, settings.public_url), settings)
    app.register_blueprint(customer_api)


def configured(app):
    return bool(app.config.get('CUSTOMER_BOT_TOKEN') and app.config.get('BOT_TOKEN')
                and app.config.get('CUSTOMER_BOT_ADMIN_IDS')
                and re.fullmatch(r'[A-Za-z0-9_-]{32,256}', app.config.get('CUSTOMER_BOT_WEBHOOK_SECRET', '')))


@customer_api.post('/webhook')
def webhook():
    if not configured(current_app):
        abort(503)
    secret = current_app.config['CUSTOMER_BOT_WEBHOOK_SECRET']
    supplied = request.headers.get('X-Telegram-Bot-Api-Secret-Token', '')
    if not hmac.compare_digest(secret.encode(), supplied.encode()):
        abort(403)
    if not request.is_json or request.content_length is None or request.content_length > 65536:
        abort(400)
    data = request.get_json(silent=True)
    try:
        receive(current_app.extensions['customer_bot'], data)
    except (ValueError, TypeError, AttributeError):
        abort(400)
    # Acknowledgement is best effort; the order and outgoing messages are durable.
    callback = data.get('callback_query')
    if isinstance(callback, dict) and isinstance(callback.get('id'), str):
        try:
            Telegram(current_app.config['CUSTOMER_BOT_TOKEN']).call('answerCallbackQuery', {'callback_query_id': callback['id']})
        except TelegramError:
            current_app.logger.warning('Не удалось подтвердить callback клиентского бота')
    return {'ok': True}


def register_commands(app):
    @app.cli.command('set-customer-bot-webhook')
    def set_webhook():
        """Configure the customer bot's commands and HTTPS webhook."""
        if not configured(current_app) or not current_app.config['APP_BASE_URL'].startswith('https://'):
            raise click.ClickException('Задайте CUSTOMER_BOT_TOKEN, CUSTOMER_BOT_WEBHOOK_SECRET, BOT_TOKEN, CUSTOMER_BOT_ADMIN_IDS и HTTPS APP_BASE_URL')
        api = Telegram(current_app.config['CUSTOMER_BOT_TOKEN'])
        try:
            configure_bot(api)
            api.call('setWebhook', {'url': current_app.config['APP_BASE_URL'] + '/customer-bot/webhook',
                'secret_token': current_app.config['CUSTOMER_BOT_WEBHOOK_SECRET'],
                'allowed_updates': ['message', 'callback_query'], 'drop_pending_updates': False})
        except TelegramError as error:
            raise click.ClickException(f'Telegram API недоступен: код {error.code}') from None
        click.echo('Webhook клиентского бота установлен')

    @app.cli.command('customer-bot-worker')
    def worker():
        """Deliver pending customer and employee messages; run as a separate process."""
        if not configured(current_app):
            raise click.ClickException('Клиентский бот не настроен')
        store = current_app.extensions['customer_bot'].store
        apis = {'customer': Telegram(current_app.config['CUSTOMER_BOT_TOKEN']),
                'admin': Telegram(current_app.config['BOT_TOKEN'])}
        while True:
            try:
                delivered = deliver(store, apis)
                if not delivered:
                    time.sleep(1)
            except Exception:
                db.session.rollback()
                current_app.logger.exception('Ошибка очереди клиентского бота')
                time.sleep(5)

    @app.cli.command('customer-bot-queue')
    def queue_status():
        store = current_app.extensions['customer_bot'].store
        with store.engine.connect() as conn:
            for target, sent, failed, count in conn.execute(
                select(outbox.c.target, outbox.c.sent, outbox.c.failed, func.count())
                .group_by(outbox.c.target, outbox.c.sent, outbox.c.failed)):
                state = 'sent' if sent else 'failed' if failed else 'pending'
                click.echo(f'{target} | {state} | {count}')

    @app.cli.command('customer-bot-retry-failed')
    def retry_failed():
        store = current_app.extensions['customer_bot'].store
        with store.transaction() as conn:
            count = conn.execute(update(outbox).where(outbox.c.failed.is_(True)).values(
                failed=False, attempts=0, available_at=time.time())).rowcount
        click.echo(f'Сообщений возвращено в очередь: {count}')

    @app.cli.command('customer-bot-orders')
    def list_orders():
        store = current_app.extensions['customer_bot'].store
        with store.engine.connect() as conn:
            for order in conn.execute(select(orders).order_by(orders.c.created_at.desc()).limit(50)).mappings():
                click.echo(f'{order["id"]} | {order["status"]} | {order["total"]} KZT')
