"""Small Bot API transport. Never log request URLs: they contain the bot token."""
import time
import requests
from sqlalchemy import select, update
from .storage import outbox

ALLOWED_UPDATES = ['message', 'callback_query']


def configure_bot(api):
    api.call('setMyCommands', {'commands': [
        {'command': 'start', 'description': 'Главное меню'},
        {'command': 'cart', 'description': 'Моя корзина'},
        {'command': 'orders', 'description': 'Мои заказы'},
        {'command': 'help', 'description': 'Доставка и помощь'},
        {'command': 'cancel', 'description': 'Отменить ввод и открыть меню'}]})
    api.call('setMyDescription', {'description': 'KoDee Desire · украшения с вашим смыслом. Выберите свой символ, оформите заказ и следите за его статусом прямо здесь.'})
    api.call('setMyShortDescription', {'short_description': 'Украшения с вашим смыслом · каталог и заказы'})


class TelegramError(Exception):
    def __init__(self, code, retry_after=0):
        self.code, self.retry_after = code, retry_after
        super().__init__(f'Telegram API error {code}')


class Telegram:
    def __init__(self, token):
        self.token = token
        self.http = requests.Session()

    def call(self, method, payload):
        if not self.token:
            raise RuntimeError('Задайте BOT_TOKEN')
        try:
            response = self.http.post(f'https://api.telegram.org/bot{self.token}/{method}', json=payload, timeout=(10, 40))
            result = response.json()
        except (requests.RequestException, ValueError):
            raise TelegramError(503) from None
        if not result.get('ok'):
            raise TelegramError(result.get('error_code', response.status_code), result.get('parameters', {}).get('retry_after', 0))
        return result.get('result')


def receive(dialog, data, queue=True):
    if not isinstance(data, dict) or type(data.get('update_id')) is not int or data['update_id'] < 0:
        raise ValueError('Invalid update')
    callback = data.get('callback_query')
    message = callback.get('message', {}) if isinstance(callback, dict) else data.get('message', {})
    if not isinstance(message, dict):
        raise ValueError('Invalid message')
    user = callback.get('from', {}) if callback else message.get('from', {})
    chat = message.get('chat', {})
    # Customer orders are private. Channel DMs and Business updates are a different mode.
    if chat.get('type') != 'private' or user.get('is_bot'):
        return []
    uid = user.get('id')
    if type(uid) is not int or uid <= 0 or chat.get('id') != uid:
        return []
    route = {'chat_id': uid}
    if message.get('message_thread_id') is not None:
        if type(message['message_thread_id']) is not int:
            raise ValueError('Invalid thread')
        route['message_thread_id'] = message['message_thread_id']
    text = message.get('text', '') if not callback else ''
    action = callback.get('data', '') if callback else ''
    if not isinstance(text, str) or not isinstance(action, str) or len(text) > 4096 or len(action.encode()) > 64:
        raise ValueError('Invalid input')
    return dialog.dispatch(data['update_id'], uid, route, text=text, action=action,
                           contact=message.get('contact') if not callback else None, queue=queue)


def deliver(store, apis, limit=20):
    """Lease each message before network I/O; expired leases are safe to retry."""
    delivered = 0
    for _ in range(limit):
        with store.transaction() as conn:
            row = conn.execute(select(outbox).where(outbox.c.sent.is_(False),
                outbox.c.failed.is_(False), outbox.c.available_at <= time.time())
                .order_by(outbox.c.id).limit(1)).mappings().first()
            if not row:
                break
            # Telegram calls have a 50 s timeout; the 120 s lease also survives
            # a worker crash without holding the order transaction lock.
            conn.execute(update(outbox).where(outbox.c.id == row['id']).values(available_at=time.time() + 120))
        try:
            api = apis.get(row['target'])
            if api is None:
                raise TelegramError(503)
            api.call(row['method'], row['payload'])
        except TelegramError as error:
            attempts = row['attempts'] + 1
            values = dict(attempts=attempts, available_at=time.time() + max(error.retry_after, min(300, 2 ** min(attempts, 8))),
                          failed=error.code in {400, 401, 403, 404} or attempts >= 12,
                          last_error=f'API {error.code}')
            if row['method'] == 'sendPhoto' and error.code == 400:
                payload = dict(row['payload'])
                payload.pop('photo', None)
                payload['text'] = payload.pop('caption')
                values.update(method='sendMessage', payload=payload, failed=False, available_at=time.time())
        else:
            values = dict(sent=True, last_error=None)
            delivered += 1
        with store.transaction() as conn:
            conn.execute(update(outbox).where(outbox.c.id == row['id']).values(**values))
    return delivered
