import unittest
import json
import re
from html.parser import HTMLParser
from urllib.parse import unquote, urlsplit
from xml.etree import ElementTree as ET

from __init__ import create_app
from db.models import db, Product


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
    def handle_starttag(self, tag, attrs):
        if tag == 'a':
            self.links.append(dict(attrs).get('href', ''))


class SeoTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app({'TESTING': True, 'SECRET_KEY': 'test',
            'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:', 'BOT_TOKEN': None,
            'APP_BASE_URL': 'http://localhost', 'TRUSTED_HOSTS': ['localhost'],
            'SESSION_COOKIE_SECURE': False})
        self.ctx = self.app.app_context()
        self.ctx.push()
        db.create_all()
        for slug, active in [('sun', True), ('hidden', False)]:
            item = Product(name='Кулон Солнце', short_name='Солнце', price=100,
                weight=1, concept='Символы', category='Кулон',
                descriptions='Символ света', slug=slug)
            item.active = active
            db.session.add(item)
        db.session.commit()
        self.client = self.app.test_client()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def test_catalog_category_product_and_sitemap(self):
        links = Links()
        links.feed(self.client.get('/shop').get_data(as_text=True))
        self.assertIn('/product/sun', links.links)
        self.assertIn('/braslety-na-niti', links.links)
        self.assertIn('/product/sun', self.client.get('/braslety-na-niti').get_data(as_text=True))
        product = self.client.get('/product/sun').get_data(as_text=True)
        self.assertIn('Кулон Солнце на нити | KoDee Desire', product)
        self.assertIn('Символ света.', product)
        self.assertIn('href="https://kodee.kz/product/sun"', product)
        self.assertIn('name="csrf_token"', product)
        sitemap = ET.fromstring(self.client.get('/sitemap.xml').data)
        urls = [node.text for node in sitemap.findall('{*}url/{*}loc')]
        self.assertIn('https://kodee.kz/product/sun', urls)
        self.assertNotIn('https://kodee.kz/product/hidden', urls)
        for url in urls:
            parsed = urlsplit(url)
            self.assertEqual((parsed.scheme, parsed.netloc), ('https', 'kodee.kz'))
            response = self.client.get(parsed.path)
            self.assertEqual(response.status_code, 200, url)
            self.assertNotIn('noindex', response.headers.get('X-Robots-Tag', ''))
        self.assertEqual(self.client.get('/product/hidden').status_code, 404)

    def test_private_pages_noindex_and_profile_redirect(self):
        for path in ['/login', '/register', '/profil', '/basket', '/admin/']:
            self.assertIn('noindex', self.client.get(path).headers.get('X-Robots-Tag', ''))
        response = self.client.get('/profil', follow_redirects=True)
        self.assertEqual([r.status_code for r in response.history], [302])
        self.assertEqual(response.request.path, '/login')
        self.assertEqual(response.status_code, 200)

    def test_complete_catalog_without_javascript(self):
        for number in range(1, 16):
            db.session.add(Product(name=f'Тест {number}', short_name='Тест', price=100,
                weight=1, concept='Тест', category='Кулон' if number <= 8 else 'Бегунок',
                descriptions='Описание', slug=f'catalog-{number:02}'))
        db.session.commit()
        expected = {'/product/' + p.slug for p in Product.query.filter_by(active=True)}
        root = ET.fromstring(self.client.get('/sitemap.xml').data)
        sitemap = {urlsplit(node.text).path for node in root.findall('{*}url/{*}loc')
                   if urlsplit(node.text).path.startswith('/product/')}
        queue, seen, reachable = ['/shop'], set(), set()
        while queue:
            path = queue.pop()
            if path in seen:
                continue
            seen.add(path)
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200, path)
            parsed = Links()
            parsed.feed(response.get_data(as_text=True))
            for link in parsed.links:
                if link.startswith('/product/'):
                    reachable.add(link)
                elif link.startswith('/category/') or link == '/braslety-na-niti':
                    queue.append(unquote(link))
        self.assertEqual(expected, sitemap, (expected - sitemap, sitemap - expected))
        self.assertEqual(expected, reachable, (expected - reachable, reachable - expected))
        for path in expected:
            self.assertEqual(self.client.get(path).status_code, 200, path)
        self.assertNotIn('/product/hidden', reachable | sitemap)
        self.assertEqual(self.client.get('/product/hidden').status_code, 404)
        self.assertGreater(len(expected), 12)

    def test_category_labels_and_product_contact(self):
        redirect = self.client.get('/category/Кулон')
        self.assertEqual(redirect.status_code, 301)
        self.assertEqual(redirect.headers['Location'], '/braslety-na-niti')
        page = self.client.get('/braslety-na-niti').get_data(as_text=True)
        self.assertIn('<h1>Кулоны желаний на нити</h1>', page)
        self.assertIn('Кулоны желаний на нити — коллекция KoDee Desire', page)
        self.assertNotIn('Кулон — украшения в каталоге', page)
        product = self.client.get('/product/sun').get_data(as_text=True)
        self.assertIn('id="productContactWhatsApp" href="https://wa.me/77003360024?text=', product)
        self.assertIn('data-product-id="1"', product)
        self.assertNotIn('Доступность материала и пробу уточняйте', product)
        self.product_without_details = Product(name='Без данных', short_name='Тест', price=0,
            weight=0, concept='', category='Новая категория', descriptions='', slug='empty')
        db.session.add(self.product_without_details)
        db.session.commit()
        page = self.client.get('/product/empty').get_data(as_text=True)
        self.assertIn('Цену уточняйте у мастерской', page)
        self.assertNotIn('<h3>Вес</h3>', page)
        self.assertNotIn('<h2>Описание</h2>', page)
        self.assertIn('<h1>Новая категория</h1>', self.client.get('/category/Новая категория').get_data(as_text=True))

    def test_homepage_does_not_list_inactive_featured_product(self):
        item = Product(name='Скрытый кулон', short_name='Тест', price=100,
            weight=1, concept='Тест', category='Кулон', descriptions='Тест', slug='beskonechnost')
        item.active = False
        db.session.add(item)
        db.session.commit()
        home = self.client.get('/').get_data(as_text=True)
        self.assertNotIn('href="/product/beskonechnost"', home)
        item.active = True
        db.session.commit()
        home = self.client.get('/').get_data(as_text=True)
        self.assertIn('href="/product/beskonechnost"', home)

    def test_intent_pages_only_link_to_matching_active_products(self):
        for slug, category, active in [('coin', 'Монеточка', True), ('runner', 'Бегунок', True),
                                        ('inactive-runner', 'Бегунок', False)]:
            item = Product(name=slug, short_name=slug, price=64000, weight=.7,
                concept='Символы', category=category, descriptions='Описание', slug=slug)
            item.active = active
            db.session.add(item)
        db.session.commit()
        bracelet = self.client.get('/braslety-na-niti').text
        self.assertIn('<h1>Кулоны желаний на нити</h1>', bracelet)
        self.assertIn('href="https://kodee.kz/braslety-na-niti"', bracelet)
        links = Links()
        links.feed(bracelet)
        self.assertEqual({link for link in links.links if link.startswith('/product/')},
                         {'/product/sun'})
        coin = self.client.get('/category/Монеточка').text
        self.assertIn('<h1>Монетки для гравировки</h1>', coin)
        links = Links()
        links.feed(coin)
        self.assertEqual({link for link in links.links if link.startswith('/product/')}, {'/product/coin'})
        runner = self.client.get('/category/Бегунок').text
        links = Links()
        links.feed(runner)
        self.assertEqual({link for link in links.links if link.startswith('/product/')}, {'/product/runner'})
        for path in ['/shop', '/braslety-na-niti', '/category/Монеточка', '/category/Бегунок']:
            links = Links()
            links.feed(self.client.get(path).text)
            for href in links.links:
                if href.startswith(('/category/', '/product/', '/braslety-na-niti')):
                    self.assertEqual(self.client.get(unquote(href)).status_code, 200, (path, href))

    def test_product_schema_uses_catalogue_facts(self):
        from db.models import Product_image
        product = Product.query.filter_by(slug='sun').one()
        db.session.add(Product_image(1, product.id, '/static/image/productImgs/sun/img1.webp'))
        db.session.commit()
        def schema():
            html = self.client.get('/product/sun').text
            scripts = re.findall(r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', html, re.S)
            self.assertEqual(len(scripts), 1)
            return json.loads(scripts[0])
        data = schema()
        self.assertEqual(data['name'], product.name)
        self.assertEqual(data['sku'], str(product.id))
        self.assertEqual(data['offers']['price'], product.price)
        self.assertEqual(data['offers']['priceCurrency'], 'KZT')
        self.assertEqual(data['image'], ['https://kodee.kz/static/image/productImgs/sun/img1.webp'])
        self.assertNotIn('availability', data['offers'])
        self.assertNotIn('aggregateRating', data)
        product.price = 0
        product.images.clear()
        db.session.commit()
        data = schema()
        self.assertNotIn('offers', data)
        self.assertNotIn('image', data)

    def test_samolet_editorial_copy_uses_current_catalogue_price(self):
        item = Product(name='Кулон «Самолёт»', short_name='Самолёт', price=65000,
            weight=.78, concept='Путешествия и приключения', category='Кулон',
            descriptions='Описание из каталога', slug='samolet')
        db.session.add(item)
        db.session.commit()
        def read():
            html = self.client.get('/product/samolet').text
            schema = json.loads(re.search(r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', html, re.S).group(1))
            return html, schema
        html, schema = read()
        self.assertIn('Кулон в форме самолёта', html)
        self.assertIn('цена 65 000 ₸', html.lower())
        self.assertIn('Кулон в форме самолёта', schema['description'])
        self.assertEqual(schema['offers']['price'], 65000)
        self.assertNotIn('из золота', html)
        item.price = 67000
        db.session.commit()
        html, schema = read()
        self.assertIn('цена 67 000 ₸', html.lower())
        self.assertEqual(schema['offers']['price'], 67000)

    def test_pendant_meta_uses_complete_sentence_and_current_facts(self):
        item = Product(name='Кулон «Дерево»', short_name='Дерево', price=46500,
            weight=.47, concept='Жизнь и процветание', category='Кулон',
            descriptions='Кулон «Дерево» - Древо жизни — символ мудрости, семейных уз и духовного роста. Следующее предложение.',
            slug='derevo')
        db.session.add(item)
        db.session.commit()
        page = self.client.get('/product/derevo').text
        self.assertIn('Древо жизни — символ семейных уз и связи поколений. Вес 0,47 г, цена 46 500 ₸.', page)
        self.assertNotIn('Следующее предложение. Вес', page)
        item.price = 47000
        db.session.commit()
        self.assertIn('цена 47 000 ₸', self.client.get('/product/derevo').text.lower())

    def test_engraving_service_and_coin_catalog_link_each_other(self):
        coin = Product(name='Гравировка золотой монетки с одной стороны 0.7г',
            short_name='Монетка', price=64000, weight=.7, concept='Минимализм',
            category='Монеточка', descriptions='Гравировка', slug='coin')
        db.session.add(coin)
        db.session.commit()
        service = Links()
        service.feed(self.client.get('/individual').text)
        self.assertIn('/category/%D0%9C%D0%BE%D0%BD%D0%B5%D1%82%D0%BE%D1%87%D0%BA%D0%B0', service.links)
        catalog = Links()
        catalog.feed(self.client.get('/category/Монеточка').text)
        self.assertIn('/individual#examples', catalog.links)
        service_html = self.client.get('/individual').text
        self.assertIn('64 000 ₸', service_html)
        self.assertIn('id="examples"', service_html)
        self.assertIn('id="individual-request"', service_html)
        self.assertIn('Будущий пример', service_html)
        self.assertIn('/product/coin', service.links)
        self.assertIn('/individual#examples', self.client.get('/shop').text)
        self.assertIn('/individual#request', self.client.get('/product/coin').text)

    def test_coin_product_links_preserve_known_side_only(self):
        for slug, side in [('gravirovka-zolotoi-monetki-s-odnoi-storony-0-7g', 'one'),
                           ('gravirovka-zolotoi-monetki-s-dvukh-storon-1-1g', 'two')]:
            db.session.add(Product(name='Монетка', short_name='Монетка', price=100, weight=.7,
                concept='Гравировка', descriptions='Монетка', category='Монеточка', slug=slug))
            db.session.commit()
            self.assertIn(f'/individual?side={side}#request', self.client.get('/product/' + slug).text)
