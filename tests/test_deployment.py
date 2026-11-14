"""Deployment configuration, tunnel setup and persistent image storage."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace as NS
from dotenv import dotenv_values
from __init__ import create_app
import test_system as fixtures
from web.app.images import publish_images
from scripts.configure_ngrok import configure


class DeploymentTests(unittest.TestCase):
    setUpClass=classmethod(fixtures.SystemTests.setUpClass.__func__)
    tearDownClass=classmethod(fixtures.SystemTests.tearDownClass.__func__)
    setUp=fixtures.SystemTests.setUp
    tearDown=fixtures.SystemTests.tearDown

    def test_tunnel_helper_preserves_ids_and_token(self):
        with tempfile.TemporaryDirectory() as folder:
            file=Path(folder)/'.env.local'
            file.write_text('DATABASE_URL=postgresql://local:fake@127.0.0.1:55439/kodee_dev\nBOT_TOKEN=123:fake\nBOT_ALLOWED_USER_IDS=1001,1002\n')
            configure('https://example.ngrok-free.app',file)
            values=dotenv_values(file)
            self.assertEqual(values['BOT_TOKEN'],'123:fake')
            self.assertEqual(values['BOT_ALLOWED_USER_IDS'],'1001,1002')
            self.assertEqual(values['WEBHOOK_URL'],'https://example.ngrok-free.app/bot/webhook')
            self.assertEqual(values['PROXY_X_PROTO'],'1')
            self.assertEqual(values['PROXY_X_HOST'],'0')
            self.assertRegex(values['BOT_WEBHOOK_SECRET'],r'^[A-Za-z0-9_-]{32,256}$')
            self.assertEqual(file.stat().st_mode & 0o777,0o600)
            secret=values['BOT_WEBHOOK_SECRET']
            configure('https://new.ngrok-free.app',file)
            self.assertEqual(dotenv_values(file)['BOT_WEBHOOK_SECRET'],secret)

    def test_tunnel_helper_refuses_production_database_file(self):
        with tempfile.TemporaryDirectory() as folder:
            file=Path(folder)/'.env.local'
            file.write_text('DATABASE_URL=postgresql://example.invalid/production\n')
            before=file.read_text()
            with self.assertRaises(ValueError):configure('https://example.ngrok-free.app',file)
            self.assertEqual(file.read_text(),before)

    def test_render_https_does_not_trust_forwarded_values(self):
        app=create_app({'TESTING':True,'SECRET_KEY':'deployment-test','SQLALCHEMY_DATABASE_URI':'sqlite:///:memory:',
            'BOT_TOKEN':None,'APP_BASE_URL':'https://demo.onrender.com','TRUSTED_HOSTS':['demo.onrender.com'],
            'PUBLIC_HTTPS':True,'TRUSTED_PROXY_CIDRS':[], 'PROXY_X_FOR':0,'PROXY_X_PROTO':0,'PROXY_X_HOST':0,'PROXY_X_PORT':0})
        response=app.test_client().get('/login',base_url='http://demo.onrender.com',headers={'X-Forwarded-Proto':'http','X-Forwarded-Host':'evil.invalid'},environ_overrides={'REMOTE_ADDR':'10.2.3.4'})
        self.assertEqual(response.status_code,200)
        self.assertIn('Strict-Transport-Security',response.headers)
        self.assertEqual(app.test_client().get('/healthz',base_url='http://evil.invalid').status_code,400)

    def test_render_legacy_postgres_url_is_normalized_without_connecting(self):
        with patch.dict(os.environ,{'DATABASE_URL':'postgres://local:fake@127.0.0.1:5432/kodee'}):
            app=create_app({'TESTING':True,'SECRET_KEY':'deployment-test','BOT_TOKEN':None,
                'APP_BASE_URL':'https://demo.onrender.com','TRUSTED_HOSTS':[],'PUBLIC_HTTPS':True,
                'TRUSTED_PROXY_CIDRS':[],'PROXY_X_FOR':0,'PROXY_X_PROTO':0,'PROXY_X_HOST':0,'PROXY_X_PORT':0})
        self.assertTrue(app.config['SQLALCHEMY_DATABASE_URI'].startswith('postgresql://'))
        self.assertEqual(app.test_client().get('/healthz',base_url='https://demo.onrender.com').status_code,200)
        with app.app_context():
            from db.models import db
            db.engine.dispose()

    def test_render_default_url_and_initial_health_without_schema(self):
        with patch.dict(os.environ,{'APP_BASE_URL':'','RENDER_EXTERNAL_URL':'https://demo.onrender.com'}):
            app=create_app({'TESTING':True,'SECRET_KEY':'deployment-test','SQLALCHEMY_DATABASE_URI':'sqlite:///:memory:',
                'BOT_TOKEN':None,'PUBLIC_HTTPS':True,'TRUSTED_HOSTS':[],'TRUSTED_PROXY_CIDRS':[],
                'PROXY_X_FOR':0,'PROXY_X_PROTO':0,'PROXY_X_HOST':0,'PROXY_X_PORT':0})
        self.assertEqual(app.config['APP_BASE_URL'],'https://demo.onrender.com')
        self.assertEqual(app.test_client().get('/healthz',base_url='https://demo.onrender.com').json,{'status':'ok'})

    def test_persistent_image_serving_and_bundled_fallback(self):
        with tempfile.TemporaryDirectory() as folder:
            source=Path(folder)/'source'
            bundled=source/'image/productImgs/test-product'
            bundled.mkdir(parents=True)
            (bundled/'img1.webp').write_bytes(b'bundled-test-image')
            with patch.object(self.app,'_static_folder',str(source)),patch.dict(self.app.config,{'PRODUCT_IMAGES_DIR':str(Path(folder)/'disk')}):
                with self.client.get('/static/image/productImgs/test-product/img1.webp') as response:
                    self.assertEqual(response.data,b'bundled-test-image')
                with publish_images('test-product',[(1,fixtures.image_bytes())]):pass
                self.assertTrue((Path(folder)/'disk/test-product/img1.webp').is_file())
                with self.client.get('/static/image/productImgs/test-product/img1.webp') as response:
                    self.assertEqual(response.status_code,200)
                    self.assertNotEqual(response.data,b'bundled-test-image')
                self.assertEqual(self.client.get('/static/image/productImgs/test-product/secret.txt').status_code,404)

    def test_bot_status_is_read_only_and_hides_secrets(self):
        token=self.app.config['BOT_TOKEN']
        with patch.object(self.bot,'get_webhook_info',return_value=NS(url='https://example.com/bot/webhook',pending_update_count=0,last_error_message=token)),patch.object(self.bot,'set_webhook') as setter:
            result=self.app.test_cli_runner().invoke(args=['bot-status'])
            self.assertEqual(result.exit_code,0)
            self.assertNotIn(token,result.output)
            setter.assert_not_called()


if __name__=='__main__':unittest.main()
