"""Integration tests for the customer bot and the shared order database."""
import tempfile
from concurrent.futures import ThreadPoolExecutor
from threading import Event
import unittest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace

from sqlalchemy import select, update, text
from __init__ import create_app
from customer_bot.storage import orders, outbox, sessions, updates
from customer_bot.telegram import deliver, TelegramError
from db.models import db, Product
from db.maintenance import upgrade_schema


class CustomerBotTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.app = create_app({'TESTING': True, 'SECRET_KEY': 'test',
            'SQLALCHEMY_DATABASE_URI': f'sqlite:///{Path(self.temp.name) / "shared.db"}',
            'APP_BASE_URL': 'https://kodee.kz', 'TRUSTED_HOSTS': ['kodee.kz'],
            'BOT_TOKEN': '123456:admin', 'BOT_ALLOWED_USER_IDS': {1001},
            'CUSTOMER_BOT_TOKEN': '123457:customer', 'CUSTOMER_BOT_WEBHOOK_SECRET': 's' * 32,
            'CUSTOMER_BOT_ADMIN_IDS': {1001}, 'PUBLIC_HTTPS': True,
            'TRUSTED_PROXY_CIDRS': [], 'PROXY_X_FOR': 0, 'PROXY_X_PROTO': 0,
            'PROXY_X_HOST': 0, 'PROXY_X_PORT': 0})
        self.ctx = self.app.app_context()
        self.ctx.push()
        upgrade_schema()
        self.product = Product(name='Клевер', short_name='Клевер', price=37000, price_chet=1000,
            weight=1, concept='Удача', category='Кулон', descriptions='Описание', slug='klever', gold=2)
        db.session.add(self.product)
        db.session.commit()
        self.bot = self.app.extensions['customer_bot']
        self.client = self.app.test_client()
        self.seq = 0

    def tearDown(self):
        db.session.remove()
        db.engine.dispose()
        self.ctx.pop()

    def send(self, action='', text='', uid=71, update_id=None):
        self.seq += 1
        return self.bot.dispatch(update_id or self.seq, uid, {'chat_id': uid}, action=action, text=text)

    def rows(self, table):
        with db.engine.connect() as conn:
            return list(conn.execute(select(table)).mappings())

    def checkout(self):
        pid = self.product.id
        self.send(f'add:{pid}')
        self.send('checkout')
        self.send(text='Анна')
        self.send(text='+7 700 123 45 67')
        self.send(text='Алматы, улица Абая, дом 12')
        result = self.send('skip_note')[0]
        return result['reply_markup']['inline_keyboard'][0][0]['callback_data']

    def test_order_is_shared_durable_and_notifies_admin(self):
        action = self.checkout()
        self.send(action, update_id=500)
        self.assertEqual(self.send(action, update_id=500), [])
        self.send(action, update_id=501)
        order, = self.rows(orders)
        self.assertEqual(order['total'], 37000)
        self.assertEqual(order['items'][0]['product_id'], self.product.id)
        self.assertEqual(order['customer']['phone'], '+77001234567')
        messages = [r for r in self.rows(outbox) if r['target'] == 'admin']
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0]['payload']['chat_id'], 1001)
        self.assertIn(order['id'], messages[0]['payload']['text'])
        self.assertIn('Клевер', messages[0]['payload']['text'])
        self.assertEqual(db.session.get(Product, self.product.id).gold, 2)
        self.send('do_cancel:' + order['id'], uid=99)
        self.assertEqual(self.rows(orders)[0]['status'], 'new')
        self.send('do_cancel:' + order['id'])
        self.assertEqual(self.rows(orders)[0]['status'], 'cancelled')
        self.assertEqual(len([r for r in self.rows(outbox) if r['target'] == 'admin']), 2)

    def test_concurrent_confirmations_create_single_order(self):
        action = self.checkout()
        def confirm(update_id):
            with self.app.app_context():
                return self.bot.dispatch(update_id, 71, {'chat_id': 71}, action=action)
        with ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(confirm, [701, 702]))
        self.assertEqual(len(self.rows(orders)), 1)
        self.assertEqual(len([r for r in self.rows(outbox) if r['target'] == 'admin']), 1)

    def test_upgrade_existing_prototype_outbox(self):
        with db.engine.begin() as conn:
            conn.execute(text('ALTER TABLE cb_outbox RENAME TO cb_outbox_new'))
            conn.execute(text('CREATE TABLE cb_outbox (id INTEGER PRIMARY KEY, method VARCHAR(40) NOT NULL, payload JSON NOT NULL, attempts INTEGER NOT NULL, available_at FLOAT NOT NULL, sent BOOLEAN NOT NULL, failed BOOLEAN NOT NULL, last_error VARCHAR(100))'))
            conn.execute(text("INSERT INTO cb_outbox (id, method, payload, attempts, available_at, sent, failed) VALUES (1, 'sendMessage', '{}', 0, 0, 0, 0)"))
        upgrade_schema()
        self.assertEqual(self.rows(outbox)[0]['target'], 'customer')
        upgrade_schema()
        self.assertEqual(len(self.rows(outbox)), 1)

    def test_order_and_notifications_rollback_together(self):
        action = self.checkout()
        with patch.object(self.bot, 'notify_staff', side_effect=RuntimeError('test')):
            with self.assertRaises(RuntimeError):
                self.send(action, update_id=600)
        self.assertEqual(self.rows(orders), [])
        self.assertFalse(any(r['id'] == 600 for r in self.rows(updates)))
        self.send(action, update_id=600)
        self.assertEqual(len(self.rows(orders)), 1)

    def test_price_and_stock_are_rechecked(self):
        action = self.checkout()
        self.product.price = 40000
        db.session.commit()
        response = self.send(action)[0]
        self.assertIn('Цена или состав изменились', response['text'])
        self.assertEqual(self.rows(orders), [])
        action = response['reply_markup']['inline_keyboard'][0][0]['callback_data']
        self.product.gold = 0
        db.session.commit()
        self.assertIn('Наличие изменилось', self.send(action)[0]['text'])
        self.assertEqual(self.rows(orders), [])

    def test_webhook_secret_and_private_chats(self):
        payload = {'update_id': 1, 'message': {'from': {'id': 71, 'is_bot': False},
            'chat': {'id': 71, 'type': 'private'}, 'text': '/start'}}
        url = '/customer-bot/webhook'
        self.assertEqual(self.client.post(url, base_url='https://kodee.kz', json=payload).status_code, 403)
        headers = {'X-Telegram-Bot-Api-Secret-Token': 's' * 32}
        self.assertEqual(self.client.post(url, base_url='https://kodee.kz', json=payload, headers=headers).status_code, 200)
        payload['update_id'] = 2
        payload['message']['chat']['type'] = 'group'
        self.client.post(url, base_url='https://kodee.kz', json=payload, headers=headers)
        self.assertEqual(len(self.rows(sessions)), 1)
        self.assertEqual(len(self.rows(updates)), 1)

    def test_delivery_retry_does_not_lose_order_or_block_other_messages(self):
        action = self.checkout()
        self.send(action)
        class API:
            def __init__(self, fail=False):
                self.fail, self.calls = fail, []
            def call(self, method, payload):
                self.calls.append((method, payload))
                if self.fail:
                    raise TelegramError(429, 45)
        customer, admin = API(True), API()
        deliver(self.bot.store, {'customer': customer, 'admin': admin}, limit=100)
        self.assertEqual(len(self.rows(orders)), 1)
        self.assertEqual(len(admin.calls), 1)
        self.assertTrue(any(row['attempts'] for row in self.rows(outbox) if row['target'] == 'customer'))
        self.assertTrue(next(row for row in self.rows(outbox) if row['target'] == 'admin')['sent'])

    def test_slow_delivery_does_not_block_customer_transactions(self):
        self.send(text='/start')
        started, release = Event(), Event()
        class SlowAPI:
            def call(self, method, payload):
                started.set()
                if not release.wait(3):
                    raise RuntimeError('Timed out')
        def run_delivery():
            with self.app.app_context():
                return deliver(self.bot.store, {'customer': SlowAPI()}, limit=1)
        with ThreadPoolExecutor(max_workers=2) as pool:
            delivery = pool.submit(run_delivery)
            try:
                self.assertTrue(started.wait(2))
                def send_message():
                    with self.app.app_context():
                        return self.bot.dispatch(999, 72, {'chat_id': 72}, text='/start')
                result = pool.submit(send_message).result(timeout=2)
                self.assertTrue(result)
            finally:
                release.set()
            self.assertEqual(delivery.result(timeout=3), 1)

    def test_staff_commands_change_status_and_notify_customer(self):
        self.send(self.checkout())
        order, = self.rows(orders)
        bot = self.app.extensions['telegram_bot']
        bot._user = SimpleNamespace(id=123456, is_bot=True, first_name='AdminBot', username='adminbot')
        def update_admin(text, actor=1001):
            payload = {'update_id': 777, 'message': {'message_id': 1, 'date': 100,
                'from': {'id': actor, 'is_bot': False, 'first_name': 'Staff'},
                'chat': {'id': actor, 'type': 'private'}, 'text': text,
                'entities': [{'type': 'bot_command', 'offset': 0, 'length': len(text.split()[0])}]}}
            return self.client.post('/bot/webhook', base_url='https://kodee.kz', json=payload,
                headers={'X-Telegram-Bot-Api-Secret-Token': 'a' * 32})
        self.app.config['BOT_WEBHOOK_SECRET'] = 'a' * 32
        with patch.object(bot, 'send_message') as send:
            update_admin(f'/order {order["id"]}')
            self.assertIn('Клевер', str(send.call_args_list))
            update_admin(f'/order_status {order["id"]} confirmed')
            self.assertEqual(self.rows(orders)[0]['status'], 'confirmed')
            self.assertTrue(any('Подтверждён' in row['payload'].get('text', '')
                                for row in self.rows(outbox) if row['target'] == 'customer'))
            update_admin(f'/order_status {order["id"]} completed')
            self.assertEqual(self.rows(orders)[0]['status'], 'confirmed')
            update_admin(f'/order_status {order["id"]} preparing', actor=9999)
            self.assertEqual(self.rows(orders)[0]['status'], 'confirmed')

    def test_staff_notifications_split_long_escaped_order_safely(self):
        from customer_bot.dialog import staff_order_messages
        item = {'name': '<' * 100, 'quantity': 1, 'price': 1, 'material': 'золото', 'color': 'красный', 'size': '17–18 см'}
        order = {'id': 'ABCDEF0123456789', 'items': [item] * 8, 'total': 8, 'user_id': 71,
                 'customer': {'name': '<' * 80, 'phone': '+77001234567', 'address': '<' * 300, 'note': '<' * 300}}
        parts = staff_order_messages(order, 'Заявка')
        self.assertGreater(len(parts), 1)
        self.assertTrue(all(len(part) <= 4096 for part in parts))
        self.assertEqual(sum(part.count('• ') for part in parts), 8)

    def test_only_authorized_recipients_can_be_configured(self):
        with self.assertRaises(ValueError):
            create_app({'TESTING': True, 'SECRET_KEY': 'test', 'SQLALCHEMY_DATABASE_URI': 'sqlite://',
                'BOT_ALLOWED_USER_IDS': {1001}, 'CUSTOMER_BOT_ADMIN_IDS': {9999}})


if __name__ == '__main__':
    unittest.main()
