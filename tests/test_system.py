"""System regressions. No production credentials or external Telegram calls."""
import contextlib
import io
import json
import os
from pathlib import Path
import re
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace as NS
from unittest.mock import Mock, patch

from PIL import Image
from sqlalchemy.exc import IntegrityError
from sqlalchemy.engine import make_url
from telebot import types

from __init__ import create_app
from db.models import db, User, Product, Product_image, Sale, Certificate, BotState
from db.maintenance import upgrade_schema
from web.app.services.user import UserService
from bot.services.handlers.callbacks.change_count import _change_product_count_core
from bot.services.handlers.messages.actions import save_product_images, action_certificate
from bot.services.fsm.database_fsm import DatabaseFSMStorage
from werkzeug.security import generate_password_hash

ROOT = Path(__file__).resolve().parents[1]


def image_bytes():
    data = io.BytesIO()
    Image.new('RGB', (16, 16), 'red').save(data, 'PNG')
    return data.getvalue()


class SystemTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        test_url = os.getenv('KODEE_TEST_DATABASE_URL')
        if test_url:
            selected = make_url(test_url)
            if not selected.drivername.startswith('postgresql') or selected.host not in {'127.0.0.1', 'localhost'} or selected.database != 'kodee_test':
                raise RuntimeError('PostgreSQL tests require the isolated local database kodee_test')
        cls.env = patch.dict(os.environ, {'ADMIN_EMAIL': 'admin@example.com', 'ADMIN_PASSWORD': 'admin-testing-password'})
        cls.env.start()
        cls.app = create_app({'TESTING': True, 'SECRET_KEY': 'test-only-key',
            'APP_BASE_URL':'http://localhost','TRUSTED_HOSTS':['localhost'],
            'TRUSTED_PROXY_CIDRS':[], 'PROXY_X_FOR':0, 'PROXY_X_PROTO':0, 'PROXY_X_HOST':0, 'PROXY_X_PORT':0,
            'SQLALCHEMY_DATABASE_URI': os.getenv('KODEE_TEST_DATABASE_URL', 'sqlite:///:memory:'),
            'SESSION_COOKIE_SECURE': False, 'BOT_TOKEN': '123456:test-only-token',
            'BOT_WEBHOOK_SECRET': 'test-only-webhook-secret-1234567890', 'BOT_ALLOWED_USER_IDS': {1001}})
        cls.app.logger.disabled = True
        # Tests retain an outer app context for DB assertions; production requests
        # get a fresh g automatically.
        @cls.app.before_request
        def reset_csrf_cache():
            from flask import g
            g.pop('csrf_token', None)
            g.pop('csrf_valid', None)

    @classmethod
    def tearDownClass(cls):
        cls.env.stop()
        with cls.app.app_context():
            db.session.remove()
            db.drop_all()
            db.engine.dispose()

    def setUp(self):
        self.context = self.app.app_context()
        self.context.push()
        db.drop_all()
        upgrade_schema()
        self.user = User(name='Tester', email='tester@example.com', password=generate_password_hash('test-password'))
        self.admin = User(name='Admin', email='admin@example.com', password=generate_password_hash('admin-testing-password'))
        self.product = Product(name='Test Product', short_name='Test', price=100, price_chet=20,
            weight=1, concept='Love', category='Кулон', descriptions='Description', slug='test-product', gold=5)
        db.session.add_all([self.user, self.admin, self.product])
        db.session.commit()
        self.client = self.app.test_client()
        self.bot = self.app.extensions['telegram_bot']
        self.bot._user = types.User(id=123456, is_bot=True, first_name='TestBot', username='test_bot')
        self.patches = [patch.object(self.bot, method, return_value=NS(message_id=1))
                        for method in ('send_message', 'edit_message_text', 'send_document')]
        for item in self.patches:
            item.start()

    def tearDown(self):
        for item in self.patches:
            item.stop()
        db.session.rollback()
        db.session.remove()
        self.context.pop()

    def csrf(self):
        data = self.client.get('/login').get_data(as_text=True)
        return re.search(r'name="csrf-token" content="([^"]+)"', data).group(1)

    def login(self, admin=False):
        csrf = self.csrf()
        return self.client.post('/login/log_user', data={'email': 'admin@example.com' if admin else 'tester@example.com',
            'password': 'admin-testing-password' if admin else 'test-password', 'csrf_token': csrf})

    def post_json(self, url, data):
        return self.client.post(url, json=data, headers={'X-CSRFToken': self.csrf()})

    def message(self, text, actor=1001, group=False):
        return {'update_id': int(time.time() * 1000), 'message': {'message_id': 1, 'date': int(time.time()),
            'chat': {'id': -100 if group else actor, 'type': 'group' if group else 'private'},
            'from': {'id': actor, 'is_bot': False, 'first_name': 'Employee'}, 'text': text,
            **({'entities': [{'type': 'bot_command', 'offset': 0, 'length': len(text)}]} if text.startswith('/') else {})}}

    def callback(self, data, actor=1001):
        return {'update_id': int(time.time() * 1000), 'callback_query': {'id': 'cb', 'chat_instance': 'test',
            'from': {'id': actor, 'is_bot': False, 'first_name': 'Employee'}, 'data': data,
            'message': {'message_id': 1, 'date': int(time.time()), 'chat': {'id': actor, 'type': 'private'},
                'from': {'id': 123456, 'is_bot': True, 'first_name': 'TestBot'}, 'text': 'Menu'}}}

    def update(self, data):
        return self.client.post('/bot/webhook', json=data,
            headers={'X-Telegram-Bot-Api-Secret-Token': self.app.config['BOT_WEBHOOK_SECRET']})

    def test_guest_public_pages_and_unknown_product(self):
        for url in ('/', '/shop', '/product/test-product', '/api/products', '/AllProductJS', '/search?query=Test',
                    '/login', '/register', '/contact', '/help/size', '/individual', '/robots.txt', '/sitemap.xml', '/.well-known/security.txt'):
            with self.subTest(url=url):
                with self.client.get(url) as response:
                    self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get('/product/missing').status_code, 404)

    def test_empty_catalog_home(self):
        db.session.delete(self.product)
        db.session.commit()
        self.assertEqual(self.client.get('/').status_code, 200)
        self.assertEqual(self.client.get('/api/products').json, [])

    def test_hidden_product_not_public(self):
        self.product.active = False
        db.session.commit()
        self.assertEqual(self.client.get('/product/test-product').status_code, 404)
        self.assertEqual(self.client.get('/AllProductJS').json, [])
        self.assertEqual(self.client.get('/search?query=Test').json, [])

    def test_stale_session_becomes_guest(self):
        with self.client.session_transaction() as state:
            state.update(user_id=99999, admin=True)
        self.assertEqual(self.client.get('/product/test-product').status_code, 200)
        with self.client.session_transaction() as state:
            self.assertNotIn('admin', state)

    def test_admin_redirect_and_no_secret_output(self):
        self.assertEqual(self.client.get('/admin/').status_code, 302)
        self.assertEqual(self.client.get('/admin/product/').status_code, 302)
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.login(admin=True)
        self.assertEqual(output.getvalue(), '')
        self.assertEqual(self.client.get('/admin/').status_code, 200)
        self.login()
        self.assertEqual(self.client.get('/admin/').status_code, 302)
        with self.client.session_transaction() as state:
            self.assertFalse(state.get('admin'))

    def test_forged_admin_flag_rejected(self):
        with self.client.session_transaction() as state:
            state.update(user_id=self.user.id, admin=True)
        self.assertEqual(self.client.get('/admin/').status_code, 302)
        self.assertEqual(self.client.get('/admin/panel').status_code, 302)

    def test_registration_validation_and_reserved_admin(self):
        from web.app.privacy import CONSENT_VERSION
        no_consent = self.client.post('/register/add_user', data={
            'name': 'Synthetic', 'email': 'synthetic@example.com', 'password': 'test-password',
            'csrf_token': self.csrf(),
        })
        self.assertEqual(no_consent.status_code, 400)
        self.assertIn('Подтвердите согласие', no_consent.text)
        for data in ({'name':'', 'email':'invalid','password':'short'},
                     {'name':'x'*26,'email':'other@example.com','password':'test-password'},
                     {'name':'Hacker','email':'ADMIN@example.com','password':'test-password'}):
            self.client.post('/register/add_user', data={**data, 'privacy_consent': CONSENT_VERSION, 'csrf_token': self.csrf()})
        self.assertEqual(User.query.count(), 2)
        result = self.client.post('/register/add_user', data={'name':'New', 'email':'New@Example.com',
            'password':'test-password','privacy_consent': CONSENT_VERSION,'csrf_token':self.csrf()})
        self.assertEqual(result.status_code, 302)
        user = User.query.filter_by(email='new@example.com').one()
        self.assertEqual(user.privacy_consent_version, CONSENT_VERSION)
        self.assertIsNotNone(user.privacy_consented_at)
        self.assertEqual(self.client.get('/profil').status_code, 200)

    def test_registration_returns_to_product_and_rejects_external_redirect(self):
        from web.app.privacy import CONSENT_VERSION
        path = '/product/samolet'
        page = self.client.get('/register', query_string={'next': path}).get_data(as_text=True)
        self.assertIn('name="next" value="/product/samolet"', page)
        error = self.client.post('/register/add_user', data={'name': 'Buyer', 'email': 'invalid',
            'password': 'test-password', 'privacy_consent': CONSENT_VERSION, 'next': path, 'csrf_token': self.csrf()})
        self.assertEqual(error.status_code, 400)
        self.assertIn('Buyer', error.get_data(as_text=True))
        result = self.client.post('/register/add_user', data={'name': 'Buyer', 'email': 'buyer@example.com',
            'password': 'test-password', 'privacy_consent': CONSENT_VERSION, 'next': path, 'csrf_token': self.csrf()})
        self.assertEqual(result.location, path)
        other = self.client.post('/register/add_user', data={'name': 'Other', 'email': 'other@example.com',
            'password': 'test-password', 'privacy_consent': CONSENT_VERSION, 'next': '//example.com', 'csrf_token': self.csrf()})
        self.assertEqual(other.location, '/')

    def test_unique_email_constraint(self):
        db.session.add(User(name='Duplicate', email='TESTER@example.com'))
        with self.assertRaises(IntegrityError):
            db.session.commit()
        db.session.rollback()

    def test_profile_password_without_new_auth_requirement(self):
        self.login()
        self.assertEqual(self.client.get('/profil').status_code, 200)
        self.client.post('/profil/update_password', data={'csrf_token':self.csrf(), 'newPass':'new-password', 'reNewPass':'new-password'})
        from werkzeug.security import check_password_hash
        self.assertTrue(check_password_hash(db.session.get(User, self.user.id).password, 'new-password'))

    def test_profile_email_change_without_confirmation(self):
        self.login()
        self.client.post('/profil/update_user',data={'csrf_token':self.csrf(),'name':'Updated','email':'NEW@example.com'})
        self.assertEqual(db.session.get(User,self.user.id).email,'new@example.com')
        self.client.get('/logout')
        response=self.client.post('/login/log_user',data={'csrf_token':self.csrf(),'email':'new@example.com','password':'test-password'})
        self.assertEqual(response.status_code,302)
        with self.client.session_transaction() as state:
            self.assertEqual(state['user_id'],self.user.id)

    def test_profile_cannot_claim_another_email(self):
        self.login()
        self.client.post('/profil/update_user', data={'csrf_token':self.csrf(),'name':'Updated', 'email':'admin@example.com'})
        self.assertEqual(db.session.get(User, self.user.id).email, 'tester@example.com')

    def test_cart_favorites_and_authentication(self):
        self.assertEqual(self.post_json('/add_basket', {'product_id':self.product.id}).status_code, 401)
        self.assertEqual(self.post_json('/add_favorite', {'product_id':self.product.id}).status_code, 401)
        self.login()
        data = {'product_id':self.product.id,'color':'красный','size':'15-16 см','material':'серебро 925'}
        self.assertTrue(self.post_json('/add_basket', data).json['success'])
        self.assertFalse(self.post_json('/add_basket', data).json['success'])
        self.assertEqual(self.post_json('/add_basket', {**data,'product_id':99999}).status_code, 404)
        self.assertEqual(self.post_json('/add_basket', {**data,'color':'invalid'}).status_code, 400)
        self.assertTrue(self.post_json('/add_favorite', {'product_id':self.product.id}).json['success'])
        self.assertEqual(self.client.get('/basket').status_code, 200)
        self.assertTrue(self.post_json('/delete_basket', {'product_id':self.product.id}).json['success'])
        self.assertEqual(db.session.get(User, self.user.id).basket, [])

    def test_json_shape_and_csrf(self):
        self.login()
        self.assertEqual(self.client.post('/add_basket',json={}).status_code, 400)
        for data in (None, [], 'bad', {'product_id':True}, {'product_id':-1}):
            self.assertEqual(self.post_json('/add_favorite', data).status_code, 400)

    def test_addresses(self):
        self.login()
        payload={'name':'Home','city':'City','street':'Street','home':'1','flat':'2'}
        result=self.post_json('/add_address', payload)
        self.assertTrue(result.json['success'])
        self.assertEqual(self.client.get('/profil').status_code, 200)
        self.assertEqual(self.post_json('/add_address', {**payload,'city':'x'*21}).status_code,400)
        self.client.post('/profil/change_address',data={'csrf_token':self.csrf(), 'addresses':result.json['address']})
        self.assertEqual(db.session.get(User,self.user.id).address,result.json['address'])

    def test_webhook_auth_and_no_public_setup(self):
        data=self.message('/start')
        self.assertEqual(self.client.post('/bot/webhook',json=data).status_code,403)
        self.assertEqual(self.client.get('/bot/setwebhook').status_code,404)
        self.assertEqual(self.update({'update_id':1}).status_code,400)
        self.assertEqual(self.update(data).status_code,200)
        self.assertIsNotNone(User.query.filter_by(telegram_id=1001).first())

    def test_bot_unauthorized_and_groups(self):
        self.update(self.message('/start',actor=999))
        self.update(self.message('/start',group=True))
        self.assertIsNone(User.query.filter_by(telegram_id=999).first())
        self.assertIsNone(User.query.filter_by(telegram_id=-100).first())
        self.bot.send_message.assert_not_called()

    def test_bot_catalog_sale_and_role(self):
        self.update(self.message('/start'))
        self.update(self.callback('catalog'))
        self.update(self.message(str(self.product.id)))
        self.update(self.callback('count:-1'))
        self.assertEqual(db.session.get(Product,self.product.id,populate_existing=True).gold,4)
        self.assertEqual(Sale.query.count(),1)
        self.update(self.callback('role:worker'))
        self.assertEqual(User.query.filter_by(telegram_id=1001).first().role,'worker')
        self.update(self.callback('role:admin'))
        self.assertEqual(User.query.filter_by(telegram_id=1001).first().role,'worker')

    def test_stock_transaction_and_nonnegative_constraint(self):
        ctx=NS(db=db, markup=NS(change_count_product=lambda:None))
        _change_product_count_core(ctx,self.product.id,'gold',-2)
        self.assertEqual(self.product.gold,3)
        self.assertEqual(Sale.query.one().quantity,2)
        with self.assertRaises(ValueError):
            _change_product_count_core(ctx,self.product.id,'gold',-4)
        with patch('bot.services.handlers.callbacks.change_count.add_sale',side_effect=RuntimeError('test failure')):
            with self.assertRaises(RuntimeError):
                _change_product_count_core(ctx,self.product.id,'gold',-1)
        self.assertEqual(db.session.get(Product,self.product.id).gold,3)
        self.product.gold=-1
        with self.assertRaises(IntegrityError):
            db.session.commit()
        db.session.rollback()

    def test_bot_edit_allowlist_and_missing_objects(self):
        self.update(self.message('/start'))
        self.update(self.callback('product_action:change'))
        self.update(self.message(str(self.product.id)))
        self.update(self.callback('product_action:change:price'))
        self.update(self.message('200'))
        self.assertEqual(db.session.get(Product,self.product.id,populate_existing=True).price,200)
        self.update(self.callback('product_action:change:slug'))
        self.assertEqual(self.product.slug,'test-product')
        self.update(self.callback('product_action:hide'))
        self.update(self.message('999999'))
        self.assertEqual(Product.query.count(),1)

    def test_bot_invalid_photo_state(self):
        self.update(self.message('/start'))
        data=self.message('')
        del data['message']['text']
        data['message']['photo']=[{'file_id':'test','file_unique_id':'unique','width':16,'height':16}]
        self.assertEqual(self.update(data).status_code,200)
        self.assertEqual(Product_image.query.count(),0)

    def test_dialog_persistence_and_expiry(self):
        first,second=DatabaseFSMStorage(),DatabaseFSMStorage()
        with first.scope(1001):
            first.set(1001,{'state':'test','nested':{}})
            first.get(1001)['nested']['value']=1
        self.assertEqual(second.get(1001)['nested']['value'],1)
        record=db.session.get(BotState,1001)
        record.expires_at=0
        db.session.commit()
        self.assertIsNone(second.get(1001))
        with second.scope(1001):
            second.clear(1001)
        self.assertIsNone(db.session.get(BotState,1001))

    def test_image_upload_and_replacement(self):
        self.login(admin=True)
        with tempfile.TemporaryDirectory() as folder, patch.object(self.app,'_static_folder',folder):
            def upload(data):
                return self.client.post('/admin/add_imgs',data={'productName':'Test Product', 'csrf_token':self.csrf(),
                    'img1':(io.BytesIO(data),'test.png')},content_type='multipart/form-data')
            self.assertEqual(upload(b'bad-data').status_code,400)
            self.assertTrue(upload(image_bytes()).json['success'])
            image=Path(folder)/'image/productImgs/test-product/img1.webp'
            with Image.open(image) as loaded:
                self.assertEqual(loaded.format,'WEBP')
            self.assertTrue(upload(image_bytes()).json['success'])
            self.assertEqual(Product_image.query.count(),1)

    def test_bot_images_use_stable_slug_and_commit(self):
        self.product.name='Renamed product'
        db.session.commit()
        ctx=NS(db=db,bot=NS(get_file=lambda _:NS(file_size=10,file_path='test'),download_file=lambda _:image_bytes(),send_message=Mock()))
        with tempfile.TemporaryDirectory() as folder, patch.object(self.app,'_static_folder',folder):
            for _ in range(2):
                save_product_images(ctx,NS(chat=NS(id=1001)),{'images':['a','b','c','d']},self.product)
                db.session.commit()
            self.assertEqual(Product_image.query.count(),4)
            self.assertTrue(all('/test-product/' in image.img1 for image in Product_image.query.all()))

    def test_simple_certificate_flow_remains(self):
        self.update(self.message('/start'))
        self.update(self.callback('certificate:add'))
        self.update(self.message('1000'))
        cert=Certificate.query.one()
        self.bot.send_document.assert_called_once()
        self.update(self.callback('certificate:activate'))
        self.update(self.message(str(cert.id)))
        self.assertIsNotNone(db.session.get(Certificate,cert.id,populate_existing=True).user_at)
        self.assertFalse((ROOT/'certificates'/f'certificate-{cert.id}.pdf').exists())

    def test_internal_errors_logged_not_sent_to_bot(self):
        with patch('bot.bot.bot.start_menu',side_effect=RuntimeError('private-test-error')):
            self.assertEqual(self.update(self.message('/start')).status_code,200)
        self.bot.send_message.assert_not_called()

    def test_security_headers_everywhere_and_nonce(self):
        for url in ('/shop','/admin/','/static/js/safe.js','/missing'):
            response=self.client.get(url)
            self.assertEqual(response.headers['X-Content-Type-Options'],'nosniff')
            self.assertIn('Content-Security-Policy',response.headers)
            response.close()
        response=self.client.get('/product/test-product')
        markup=response.get_data(as_text=True)
        nonce=re.search(r"'nonce-([^']+)'",response.headers['Content-Security-Policy']).group(1)
        self.assertTrue(all(nonce in tag for tag in re.findall(r'<script[^>]*>',markup)))
        self.assertNotIn('onclick=',markup)

    def test_admin_edit_form_has_csrf(self):
        self.login(admin=True)
        response=self.client.get(f'/admin/product/edit/?id={self.product.id}')
        self.assertEqual(response.status_code,200)
        self.assertIn('name="csrf_token"',response.get_data(as_text=True))

    def test_seed_catalog_is_idempotent(self):
        runner=self.app.test_cli_runner()
        first=runner.invoke(args=['seed-products'])
        self.assertEqual(first.exit_code,0,first.output)
        count=Product.query.count()
        self.assertGreater(count,1)
        second=runner.invoke(args=['seed-products'])
        self.assertEqual(second.exit_code,0,second.output)
        self.assertEqual(Product.query.count(),count)

    def test_admin_can_create_image_record(self):
        self.login(admin=True)
        response=self.client.post('/admin/product_image/new/',data={'csrf_token':self.csrf(),
            'product':str(self.product.id),'num':'1','img1':'/static/image/productImgs/test-product/img1.webp'})
        self.assertEqual(response.status_code,302)
        self.assertEqual(Product_image.query.count(),1)

    def test_admin_can_edit_user(self):
        self.login(admin=True)
        data = {'csrf_token':self.csrf(),'name':'Updated','last_name':'','user_name':'','first_name':'',
                'phone':'','email':'tester@example.com','address':'','role':'seller','material':'gold',
                'favourites':'[]','basket':'[]'}
        response=self.client.post(f'/admin/user/edit/?id={self.user.id}',data=data)
        self.assertEqual(response.status_code,302)
        self.assertEqual(db.session.get(User,self.user.id,populate_existing=True).name,'Updated')

    def test_duplicate_image_constraint(self):
        for _ in range(2):
            db.session.add(Product_image(1,self.product.id,'/static/image/productImgs/test-product/img1.webp'))
        with self.assertRaises(IntegrityError):
            db.session.commit()
        db.session.rollback()

    def test_admin_delete_preserves_sale(self):
        product_id = self.product.id
        _change_product_count_core(NS(db=db,markup=NS(change_count_product=lambda:None)),product_id,'gold',-1)
        self.login(admin=True)
        response=self.client.post('/admin/product/delete/',data={'id':product_id,'csrf_token':self.csrf()})
        self.assertEqual(response.status_code,302)
        self.assertIsNone(Product.query.filter_by(id=product_id).first())
        self.assertIsNone(Sale.query.one().product_id)

    def test_admin_can_save_existing_unique_slug(self):
        self.login(admin=True)
        data = {field: str(getattr(self.product, field)) for field in
            ('name','short_name','price','price_chet','weight','concept','category','descriptions','G',
             'gold','silver','form_gold','form_silver','slug')}
        data.update(price='250', active='y', csrf_token=self.csrf())
        response = self.client.post(f'/admin/product/edit/?id={self.product.id}', data=data)
        self.assertEqual(response.status_code, 302, response.get_data(as_text=True)[-2000:])
        self.assertEqual(db.session.get(Product,self.product.id,populate_existing=True).price,250)

    def test_product_wizard_images_and_delete_keep_sales_history(self):
        self.update(self.message('/start'))
        self.update(self.callback('product_action:add'))
        for value in ('New Product', 'New', '200', '30', '1.5', 'Love', 'Кулон', 'Description', '10'):
            self.update(self.message(value))
        with tempfile.TemporaryDirectory() as folder, patch.object(self.app, '_static_folder', folder), \
                patch.object(self.bot, 'get_file', return_value=NS(file_size=100, file_path='file')), \
                patch.object(self.bot, 'download_file', return_value=image_bytes()):
            for _ in range(4):
                payload = self.message('')
                del payload['message']['text']
                payload['message']['photo'] = [{'file_id': 'file', 'file_unique_id': 'unique', 'width': 16, 'height': 16}]
                self.assertEqual(self.update(payload).status_code, 200)
            created = Product.query.filter_by(slug='new-product').one()
            self.assertEqual(Product_image.query.filter_by(product_id=created.id).count(), 4)
        _change_product_count_core(NS(db=db, markup=NS(change_count_product=lambda:None)), self.product.id, 'gold', -1)
        self.update(self.callback('product_action:delete'))
        self.update(self.message(str(self.product.id)))
        self.update(self.callback('product_action:delete:yes'))
        self.assertIsNone(Product.query.filter_by(id=self.product.id).first())
        self.assertIsNone(Sale.query.one().product_id)

    def test_image_files_rollback_on_failure(self):
        from web.app.images import publish_images
        with tempfile.TemporaryDirectory() as folder, patch.object(self.app, '_static_folder', folder):
            with publish_images('test-product', [(1, image_bytes())]):
                pass
            target = Path(folder) / 'image/productImgs/test-product/img1.webp'
            before = target.read_bytes()
            with self.assertRaises(RuntimeError):
                with publish_images('test-product', [(1, image_bytes()), (2, image_bytes())]):
                    raise RuntimeError('simulated DB failure')
            self.assertEqual(target.read_bytes(), before)
            self.assertFalse((target.parent / 'img2.webp').exists())

    def test_migration_is_idempotent_and_preserves_rows(self):
        runner = self.app.test_cli_runner()
        for _ in range(2):
            result = runner.invoke(args=['upgrade-db'])
            self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual(User.query.count(), 2)
        self.assertEqual(Product.query.count(), 1)

    def test_migration_rejects_duplicate_legacy_accounts(self):
        from sqlalchemy import text
        db.session.remove()
        with db.engine.begin() as connection:
            connection.execute(text('DROP INDEX uq_users_email_normalized'))
        db.session.add(User(name='Legacy', email='TESTER@example.com'))
        db.session.commit()
        result = self.app.test_cli_runner().invoke(args=['upgrade-db'])
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn('Дубликаты', result.output)
        self.assertEqual(User.query.count(), 3)

    def test_bot_setup_is_explicit_and_uses_secret(self):
        with patch.object(self.bot, 'set_my_commands') as commands, patch.object(self.bot, 'set_webhook') as webhook, \
                patch.dict(self.app.config, {'WEBHOOK_URL':'https://example.com/bot/webhook'}):
            result = self.app.test_cli_runner().invoke(args=['set-bot-webhook'])
            self.assertEqual(result.exit_code, 0, result.output)
            self.assertEqual(webhook.call_args.kwargs['secret_token'], self.app.config['BOT_WEBHOOK_SECRET'])
            commands.assert_called_once()

    @unittest.skipUnless(os.getenv('KODEE_TEST_DATABASE_URL','').startswith('postgresql'), 'Requires isolated PostgreSQL')
    def test_concurrent_dialog_updates_are_serialized(self):
        def advance(_):
            with self.app.app_context():
                fsm=DatabaseFSMStorage()
                with fsm.scope(1001):
                    data=fsm.get(1001) or {'count':0}
                    data['count']+=1
                    fsm.set(1001,data)
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(advance,range(8)))
        self.assertEqual(DatabaseFSMStorage().get(1001)['count'],8)

    def test_action_logs_authentication_and_mutations_without_secrets(self):
        with patch.object(self.app.logger, 'info') as info:
            self.client.post('/login/log_user', data={'csrf_token': self.csrf(),
                'email': 'tester@example.com', 'password': 'wrong-password'})
            self.login()
            self.post_json('/add_favorite', {'product_id': self.product.id})
            self.client.get('/logout')
        events = [json.loads(call.args[1]) for call in info.call_args_list
                  if call.args and call.args[0] == 'user_action %s']
        self.assertEqual([(e['action'], e['outcome']) for e in events],
                         [('login', 'failure'), ('login', 'success'),
                          ('favorite.toggled', 'success'), ('logout', 'success')])
        self.assertEqual([e['actor_id'] for e in events], [None, self.user.id, self.user.id, self.user.id])
        self.assertEqual(events[2]['product_id'], self.product.id)
        self.assertNotIn('wrong-password', json.dumps(events))
        self.assertNotIn('test-password', json.dumps(events))
        self.assertNotIn('tester@example.com', json.dumps(events))

    def test_action_logs_admin_and_telegram_changes(self):
        with patch.object(self.app.logger, 'info') as info:
            self.login(admin=True)
            product_id = self.product.id
            self.client.post('/admin/product/delete/', data={'id': product_id, 'csrf_token': self.csrf()})
            self.update(self.message('/start'))
            self.update(self.callback('role:worker'))
        events = [json.loads(call.args[1]) for call in info.call_args_list
                  if call.args and call.args[0] == 'user_action %s']
        deleted = next(e for e in events if e['action'] == 'admin.deleted')
        self.assertEqual((deleted['actor_id'], deleted['entity'], deleted['entity_id']),
                         (self.admin.id, 'Product', product_id))
        changed = next(e for e in events if e['action'] == 'user.role_changed')
        self.assertEqual((changed['source'], changed['actor_id'], changed['role']),
                         ('telegram', 1001, 'worker'))

    @unittest.skipUnless(os.getenv('KODEE_TEST_DATABASE_URL','').startswith('postgresql'), 'Requires isolated PostgreSQL')
    def test_concurrent_sales_do_not_oversell(self):
        product_id=self.product.id
        db.session.remove()
        def sell(_):
            with self.app.app_context():
                try:
                    _change_product_count_core(NS(db=db,markup=NS(change_count_product=lambda:None)),product_id,'gold',-1)
                    return True
                except ValueError:
                    return False
        with ThreadPoolExecutor(max_workers=8) as pool:
            results=list(pool.map(sell,range(12)))
        self.assertEqual(sum(results),5)
        self.assertEqual(db.session.get(Product,product_id).gold,0)
        self.assertEqual(Sale.query.count(),5)


if __name__=='__main__':
    unittest.main()
