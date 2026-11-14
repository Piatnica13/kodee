"""Transport-independent customer journey. All prices and totals come from catalog."""
from datetime import datetime, timezone
from html import escape
import re
import secrets
import time
from sqlalchemy import select, insert, update
from .storage import sessions, updates, orders, events, outbox

MATERIAL = 'Золото 585'
SIZES = ['Меньше 12 см', '12–14 см', '15–16 см', '17–18 см', 'Больше 18 см']
COLORS = ['Чёрный', 'Красный']
STATUSES = {'new': 'Ожидает подтверждения', 'confirmed': 'Подтверждён', 'preparing': 'Готовим заказ',
            'shipped': 'Передан в доставку', 'completed': 'Выполнен', 'cancelled': 'Отменён'}
TRANSITIONS = {'new': {'confirmed', 'cancelled'}, 'confirmed': {'preparing', 'cancelled'},
               'preparing': {'shipped', 'cancelled'}, 'shipped': {'completed'}, 'completed': set(), 'cancelled': set()}


def money(value):
    return f'{value:,}'.replace(',', ' ') + ' ₸'


def button(text, action):
    return {'text': text, 'callback_data': action}


def screen(text, rows=(), image=None):
    return {'text': text, 'reply_markup': {'inline_keyboard': list(rows)}, **({'image': image} if image else {})}


def home_button():
    return [button('⌂ Главное меню', 'home')]


def fresh():
    return {'step': '', 'cart': [], 'favorites': [], 'draft': {}, 'revision': 0}


def staff_order_messages(order, title):
    """Render complete order details in Telegram-sized HTML messages."""
    customer = order['customer']
    heading = f'<b>{escape(title)} #{order["id"]}</b>'
    sections = [f'• {escape(i["name"])} × {i["quantity"]} · {money(i["price"])}\n'
                f'  {escape(i["material"])} · {escape(i["color"])} · {escape(i["size"])}'
                for i in order['items']]
    sections.append(f'<b>Итого: {money(order["total"])}</b> без доставки\n'
        f'Получатель: {escape(customer["name"])}\nТелефон: {escape(customer["phone"])}\n'
        f'Адрес: {escape(customer["address"])}\n'
        f'Пожелания: {escape(customer.get("note") or "Нет")}\n'
        f'Telegram ID: {order["user_id"]}')
    parts, current = [], heading
    for section in sections:
        if len(current) + len(section) + 2 > 4000:
            parts.append(current)
            current = heading
        current += '\n\n' + section
    parts.append(current)
    return parts


class Dialog:
    def __init__(self, store, catalog, settings):
        self.store, self.catalog, self.settings = store, catalog, settings

    def dispatch(self, update_id, user_id, route, text='', action='', contact=None, queue=True):
        """State, orders, deduplication and outgoing messages commit in one transaction."""
        key = ':'.join(str(route.get(k, '')) for k in ('chat_id', 'message_thread_id', 'direct_messages_topic_id')) + f':{user_id}'
        now = time.time()
        with self.store.transaction() as conn:
            if conn.execute(select(updates.c.id).where(updates.c.id == update_id)).first():
                return []
            conn.execute(insert(updates).values(id=update_id, created_at=now))
            existing = conn.execute(select(sessions).where(sessions.c.key == key)).mappings().first()
            state = dict(existing['state']) if existing else fresh()
            if now - (existing['updated_at'] if existing else now) > 86400:
                state.update(step='', draft={})
            try:
                result = self.handle(conn, state, user_id, key, route, text.strip(), action, contact)
            except (ValueError, IndexError):
                result = screen('Не удалось выполнить действие. Откройте товар заново или вернитесь в меню.', [home_button()])
            state['revision'] += 1
            values = dict(user_id=user_id, state=state, updated_at=now)
            if existing:
                conn.execute(update(sessions).where(sessions.c.key == key).values(**values))
            else:
                conn.execute(insert(sessions).values(key=key, **values))
            if queue:
                self.enqueue(conn, route, result)
            return [result]

    def enqueue(self, conn, route, result):
        payload = {**route, 'parse_mode': 'HTML', 'reply_markup': result['reply_markup']}
        image = result.get('image')
        if image and image.startswith('/') and self.settings.public_url:
            image = self.settings.public_url.rstrip('/') + image
        if image and image.startswith('https://'):
            payload.update(photo=image, caption=result['text'])
            method = 'sendPhoto'
        else:
            payload['text'] = result['text']
            method = 'sendMessage'
        conn.execute(insert(outbox).values(target='customer', method=method, payload=payload, attempts=0, available_at=time.time(), sent=False, failed=False))

    def home(self, state):
        count = sum(i['quantity'] for i in state['cart'])
        return screen('<b>KoDee Desire</b>\nУкрашения с вашим смыслом.\n\n'
                      'Найдите свой символ, выберите детали — и мы бережно подготовим ваш заказ.', [
            [button('✧ Выбрать украшение', 'catalog:0')],
            [button(f'Корзина · {count}', 'cart'), button('♡ Избранное', 'favorites')],
            [button('Мои заказы', 'orders'), button('Доставка и помощь', 'help')]])

    def catalog_screen(self, state, page=0, favorites=False):
        items = self.catalog.all()
        if favorites:
            items = [p for p in items if p['id'] in state['favorites']]
        query = state.get('query', '').casefold() if not favorites else ''
        concept = state.get('concept', '') if not favorites else ''
        items = [p for p in items if (not query or query in (p['name'] + ' ' + p['concept']).casefold())
                 and (not concept or p['concept'] == concept)]
        title = 'Избранное' if favorites else 'Коллекция символов'
        if not items:
            return screen(f'<b>{title}</b>\n\n' + ('Сохраните понравившиеся украшения с помощью ♡ в карточке товара.' if favorites else 'Ничего не нашлось. Попробуйте другое название или смысл.'),
                          [[button('Все украшения', 'clear_filters')], home_button()])
        page = max(0, min(page, (len(items) - 1) // 5))
        selected = items[page * 5:page * 5 + 5]
        rows = [[button(f'{p["name"]} · {money(p["price"])}', f'product:{p["id"]}')] for p in selected]
        pages = (len(items) + 4) // 5
        if pages > 1:
            prefix = 'favorites_page' if favorites else 'catalog'
            rows.append(([button('←', f'{prefix}:{page-1}')] if page else []) +
                        [button(f'{page + 1} / {pages}', 'noop')] +
                        ([button('→', f'{prefix}:{page+1}')] if page + 1 < pages else []))
        if not favorites:
            rows += [[button('⌕ Поиск', 'search'), button('Выбрать по смыслу', 'concepts')]]
            if query or concept:
                rows += [[button('Сбросить фильтры', 'clear_filters')]]
        rows += [[button('Корзина', 'cart'), button('⌂ Меню', 'home')]]
        subtitle = escape(concept or (f'Поиск: {query}' if query else 'Маленькие символы. Большие истории.'))
        return screen(f'<b>{title}</b>\n{subtitle}\n\nНайдено: {len(items)}. Выберите украшение ↓', rows)

    def product_screen(self, state, pid):
        product = self.catalog.get(pid)
        if not product:
            return screen('Это украшение сейчас недоступно.', [[button('В каталог', 'catalog:0')]])
        state['selected'] = pid
        state['variant'] = state.get('variant', {'size': 3, 'color': 0})
        variant = state['variant']
        favorite = pid in state['favorites']
        stock = 'В наличии' if product['stock'] > 0 else 'Сейчас нет в наличии'
        text = (f'<b>{escape(product["name"])}</b>\n{escape(product["concept"])}\n\n'
                f'{escape(product["description"][:510])}\n\n'
                f'<b>{money(product["price"])}</b> · {MATERIAL}\n{stock}\n'
                f'Шнур: {COLORS[variant["color"]]} · {SIZES[variant["size"]]}')
        rows = [[button(f'Шнур: {COLORS[variant["color"]]} ↻', f'color:{pid}'),
                 button(f'Размер: {SIZES[variant["size"]]}', f'sizes:{pid}')]]
        if product['stock'] > 0:
            rows.append([button('＋ В корзину', f'add:{pid}')])
        rows += [[button('♥ Сохранено' if favorite else '♡ Сохранить', f'favorite:{pid}'), button('Корзина', 'cart')],
                 [button('← Коллекция', 'catalog:0'), button('⌂ Меню', 'home')]]
        return screen(text, rows, product.get('image'))

    def priced_items(self, state):
        result = []
        for item in state['cart']:
            p = self.catalog.get(item['product_id'])
            result.append({**item, 'name': p['name'] if p else 'Товар недоступен', 'price': p['price'] if p else 0,
                           'available': bool(p and p['stock'] >= sum(x['quantity'] for x in state['cart'] if x['product_id'] == item['product_id']))})
        return result

    def cart_screen(self, state, notice=''):
        items = self.priced_items(state)
        if not items:
            return screen('<b>Ваша корзина</b>\n\nЗдесь будет то, что откликнулось именно вам.',
                          [[button('✧ Выбрать украшение', 'catalog:0')], home_button()])
        lines, rows = [], []
        for index, item in enumerate(items, 1):
            lines.append(f'{index}. <b>{escape(item["name"])}</b>\n'
                         f'{item["color"]} · {item["size"]}\n'
                         f'{item["quantity"]} × {money(item["price"])}' + (' · Недоступен' if not item['available'] else ''))
            ident = item['key']
            rows.append([button(f'− {index}', f'dec:{ident}'), button(f'{item["quantity"]} шт.', 'noop'),
                         button(f'＋ {index}', f'inc:{ident}'), button('Удалить', f'remove:{ident}')])
        total = sum(i['price'] * i['quantity'] for i in items)
        rows += [[button('Оформить заказ →', 'checkout')], [button('Продолжить выбор', 'catalog:0')], home_button()]
        return screen((escape(notice) + '\n\n' if notice else '') + '<b>Ваша корзина</b>\n\n' + '\n\n'.join(lines) +
                      f'\n\n<b>Итого: {money(total)}</b>\nБез стоимости доставки.', rows)

    def prompt(self, state):
        prompts = {
            'name': ('01 / 04 · Получатель', 'Как вас зовут? Напишите имя получателя.'),
            'phone': ('02 / 04 · Контакт', 'Напишите номер телефона с кодом страны, например +7 700 123 45 67.'),
            'address': ('03 / 04 · Доставка', 'Напишите город и полный адрес: улицу, дом и квартиру.\n\n' + self.settings.delivery_note),
            'note': ('04 / 04 · Пожелания', 'Упаковка в подарок, особый размер или другие детали? Напишите пожелания или пропустите шаг.'),
        }
        title, body = prompts[state['step']]
        rows = [[button('Без пожеланий', 'skip_note')]] if state['step'] == 'note' else []
        rows += [[button('← Назад', 'back'), button('Отменить оформление', 'cancel_checkout')]]
        return screen(f'<b>{title}</b>\n\n{escape(body)}', rows)

    def confirm_screen(self, state):
        items = self.priced_items(state)
        total = sum(i['price'] * i['quantity'] for i in items)
        state['quote'] = [{k: i[k] for k in ('key', 'price', 'quantity')} for i in items]
        state['confirm_token'] = secrets.token_hex(6)
        state['step'] = 'confirm'
        d = state['draft']
        lines = '\n'.join(f'• {escape(i["name"])} × {i["quantity"]} · {money(i["price"] * i["quantity"])}' for i in items)
        return screen(f'<b>Всё верно?</b>\n\n{lines}\n\n<b>Украшения: {money(total)}</b>\n'
                      f'\nПолучатель: {escape(d["name"])}\nТелефон: {escape(d["phone"])}\nАдрес: {escape(d["address"])}\n'
                      f'Пожелания: {escape(d.get("note") or "Без пожеланий")}\n\n'
                      f'{escape(self.settings.delivery_note)}\n\n'
                      'Отправляя заявку, вы разрешаете использовать указанные контактные данные для обработки заказа. '
                      'Оплата и резервирование на этом шаге не выполняются.',
                      [[button('✓ Отправить заказ', f'confirm:{state["confirm_token"]}')],
                       [button('Изменить данные', 'edit_checkout'), button('В корзину', 'cancel_checkout')]])

    def handle(self, conn, state, uid, key, route, text, action, contact):
        if text.split(' ', 1)[0] in {'/start', '/menu', '/cancel'} or action == 'home':
            state.update(step='', draft={})
            return self.home(state)
        if text == '/cart':
            action = 'cart'
        if text == '/orders':
            action = 'orders'
        if text == '/help':
            action = 'help'
        if action == 'noop':
            return screen('Продолжите выбор с помощью кнопок ниже.', [[button('Коллекция', 'catalog:0'), button('Корзина', 'cart')]])
        if action in {'help', 'privacy'}:
            state['step'] = ''
            return screen('<b>С заботой о вашем заказе</b>\n\n'
                          '<b>Как заказать</b>\nВыберите украшение, цвет и размер шнура. Добавьте в корзину и заполните данные получателя.\n\n'
                          f'<b>Доставка</b>\n{escape(self.settings.delivery_note)}\n\n'
                          '<b>Оплата</b>\nПосле согласования заказа. Бот не запрашивает данные карты.\n\n'
                          '<b>Отмена</b>\nДо подтверждения заказ можно отменить в разделе «Мои заказы».\n\n'
                          '<b>Ваши данные</b>\nИмя, телефон и адрес сохраняются для обработки заказа. Не указывайте лишние личные сведения.\n\n'
                          'Консультант в боте появится позже.', [home_button()])
        if action.startswith('catalog:') or action == 'clear_filters':
            state['step'] = ''
            if action == 'clear_filters':
                state.update(query='', concept='')
            return self.catalog_screen(state, int(action.split(':')[1]) if ':' in action else 0)
        if action == 'search':
            state['step'] = 'search'
            return screen('<b>Найдём ваш символ</b>\n\nНапишите название или смысл: например, «Клевер» или «Любовь».', [home_button()])
        if action == 'concepts':
            concepts = sorted({p['concept'] for p in self.catalog.all() if p['concept']})
            state['concept_options'] = concepts
            return screen('<b>Что для вас важно?</b>\nВыберите историю своего украшения.',
                          [[button(c, f'concept:{i}')] for i, c in enumerate(concepts)] + [[button('Все украшения', 'clear_filters')]])
        if action.startswith('concept:'):
            state.update(concept=state.get('concept_options', [])[int(action.split(':')[1])], query='')
            return self.catalog_screen(state)
        if action == 'favorites' or action.startswith('favorites_page:'):
            state['step'] = ''
            return self.catalog_screen(state, int(action.split(':')[1]) if ':' in action else 0, favorites=True)
        if action.startswith(('product:', 'favorite:', 'color:', 'sizes:', 'size:', 'add:')):
            parts = action.split(':')
            kind, pid = parts[0], int(parts[1])
            state['step'] = ''
            p = self.catalog.get(pid)
            if not p:
                return screen('Украшение больше недоступно.', [[button('Коллекция', 'catalog:0')]])
            v = state.setdefault('variant', {'size': 3, 'color': 0})
            if kind == 'favorite':
                if pid in state['favorites']:
                    state['favorites'].remove(pid)
                elif len(state['favorites']) < 100:
                    state['favorites'].append(pid)
            elif kind == 'color':
                v['color'] = 1 - v['color']
            elif kind == 'sizes':
                return screen('<b>Размер шнура</b>\nВыберите комфортный обхват запястья. Особые пожелания можно добавить при оформлении.',
                              [[button(size, f'size:{pid}:{i}')] for i, size in enumerate(SIZES)] + [[button('← К украшению', f'product:{pid}')]])
            elif kind == 'size':
                size = int(parts[2])
                if not 0 <= size < len(SIZES):
                    raise ValueError('size')
                v['size'] = size
            elif kind == 'add':
                if sum(i['quantity'] for i in state['cart'] if i['product_id'] == pid) >= p['stock']:
                    return self.cart_screen(state, 'Больше экземпляров сейчас нет в наличии.')
                ident = f'{pid}-{v["size"]}-{v["color"]}'
                item = next((i for i in state['cart'] if i['key'] == ident), None)
                if item:
                    if item['quantity'] < 10:
                        item['quantity'] += 1
                elif len(state['cart']) < 8:
                    state['cart'].append(dict(key=ident, product_id=pid, quantity=1, material=MATERIAL,
                                              color=COLORS[v['color']], size=SIZES[v['size']]))
                else:
                    return self.cart_screen(state, 'В одном заказе можно оформить до 8 разных вариантов.')
                return screen(f'<b>В вашей корзине ✓</b>\n\n{escape(p["name"])}\n{COLORS[v["color"]]} · {SIZES[v["size"]]}\n{money(p["price"])}',
                              [[button('Оформить заказ →', 'checkout')], [button('В корзину', 'cart'), button('Ещё украшения', 'catalog:0')]])
            return self.product_screen(state, pid)
        if action == 'cart' or action.startswith(('inc:', 'dec:', 'remove:')):
            state['step'] = ''
            if ':' in action:
                kind, ident = action.split(':', 1)
                item = next((i for i in state['cart'] if i['key'] == ident), None)
                if item:
                    p = self.catalog.get(item['product_id'])
                    if kind == 'remove' or (kind == 'dec' and item['quantity'] == 1):
                        state['cart'].remove(item)
                    elif kind == 'dec':
                        item['quantity'] -= 1
                    elif p and item['quantity'] < 10 and sum(i['quantity'] for i in state['cart'] if i['product_id'] == p['id']) < p['stock']:
                        item['quantity'] += 1
                    else:
                        return self.cart_screen(state, 'Достигнуто доступное количество.')
            return self.cart_screen(state)
        if action in {'checkout', 'edit_checkout'}:
            items = self.priced_items(state)
            if not items or any(not i['available'] for i in items):
                return self.cart_screen(state, 'Проверьте наличие товаров перед оформлением.')
            state.update(step='name', draft={})
            return self.prompt(state)
        if action == 'cancel_checkout':
            state.update(step='', draft={})
            return self.cart_screen(state)
        if action == 'back' and state['step'] in {'name', 'phone', 'address', 'note'}:
            steps = ['name', 'phone', 'address', 'note']
            index = steps.index(state['step'])
            if index == 0:
                state['step'] = ''
                return self.cart_screen(state)
            state['step'] = steps[index - 1]
            return self.prompt(state)
        if action == 'skip_note' and state['step'] == 'note':
            state['draft']['note'] = ''
            return self.confirm_screen(state)
        if action.startswith('confirm:'):
            if state['step'] != 'confirm' or action.split(':')[1] != state.get('confirm_token'):
                return screen('Эта кнопка подтверждения уже неактуальна. Проверьте свои заказы или откройте корзину.',
                              [[button('Мои заказы', 'orders'), button('Корзина', 'cart')]])
            items = self.priced_items(state)
            if not items or any(not i['available'] for i in items):
                state['step'] = ''
                return self.cart_screen(state, 'Наличие изменилось. Пожалуйста, обновите корзину.')
            quote = [{k: i[k] for k in ('key', 'price', 'quantity')} for i in items]
            if quote != state.get('quote'):
                result = self.confirm_screen(state)
                result['text'] = 'Цена или состав изменились. Проверьте новый итог.\n\n' + result['text']
                return result
            oid, now = secrets.token_hex(8).upper(), time.time()
            values = dict(id=oid, user_id=uid, session_key=key, route=route, items=items,
                          total=sum(i['price'] * i['quantity'] for i in items), customer=state['draft'],
                          status='new', created_at=now, updated_at=now)
            conn.execute(insert(orders).values(**values))
            conn.execute(insert(events).values(kind='order.created', order_id=oid, payload={'order_id': oid, 'version': 1}, created_at=now, exported=False))
            self.notify_staff(conn, values, 'Новая заявка')
            state.update(step='', cart=[], draft={}, confirm_token='')
            return screen(f'<b>Заказ #{oid} принят ♡</b>\n\n'
                          f'Сумма украшений: <b>{money(values["total"])}</b>\nСтатус: ожидает подтверждения.\n\n'
                          'Заявка сохранена. Резерв, оплату и доставку согласуем отдельно. Следить за заказом можно здесь.',
                          [[button('Открыть заказ', f'order:{oid}')], home_button()])
        if action == 'orders':
            state['step'] = ''
            rows = conn.execute(select(orders).where(orders.c.user_id == uid).order_by(orders.c.created_at.desc()).limit(10)).mappings().all()
            return screen('<b>Мои заказы</b>\n\n' + ('Последние 10 заказов. Выберите заказ, чтобы посмотреть детали.' if rows else 'Пока заказов нет. Найдём ваше украшение?'),
                          [[button(f'#{o["id"]} · {STATUSES[o["status"]]}', f'order:{o["id"]}')] for o in rows] + [home_button()])
        if action.startswith(('order:', 'cancel_order:', 'do_cancel:')):
            kind, oid = action.split(':', 1)
            order = conn.execute(select(orders).where(orders.c.id == oid, orders.c.user_id == uid)).mappings().first()
            if not order:
                return screen('Заказ не найден.', [[button('Мои заказы', 'orders')]])
            if kind == 'cancel_order' and order['status'] == 'new':
                return screen(f'<b>Отменить заказ #{oid}?</b>\nЭто действие нельзя отменить. Вы сможете оформить новый заказ.',
                              [[button('Да, отменить', f'do_cancel:{oid}')], [button('Сохранить заказ', f'order:{oid}')]])
            if kind == 'do_cancel' and order['status'] == 'new':
                self.change_status(conn, order, 'cancelled', notify=False)
                self.notify_staff(conn, order, 'Заявка отменена покупателем')
                order = {**order, 'status': 'cancelled'}
            date = datetime.fromtimestamp(order['created_at'], timezone.utc).strftime('%d.%m.%Y')
            lines = '\n'.join(f'• {escape(i["name"])} × {i["quantity"]}\n  {i["color"]} · {i["size"]}' for i in order['items'])
            rows = [[button('Отменить заказ', f'cancel_order:{oid}')]] if order['status'] == 'new' else []
            return screen(f'<b>Заказ #{oid}</b> · {date}\n{STATUSES[order["status"]]}\n\n{lines}\n\n'
                          f'<b>{money(order["total"])}</b> · без доставки\nАдрес: {escape(order["customer"]["address"])}',
                          rows + [[button('← Мои заказы', 'orders')], home_button()])
        if not action and state['step'] == 'search':
            state.update(query=text[:80], concept='', step='')
            return self.catalog_screen(state)
        if not action and state['step'] in {'name', 'phone', 'address', 'note'}:
            field = state['step']
            if field == 'phone' and contact:
                if contact.get('user_id') != uid:
                    return screen('Отправьте свой контакт или введите номер вручную.', [[button('← Назад', 'back')]])
                text = contact.get('phone_number', '')
            if field == 'phone':
                normalized = re.sub(r'[\s()\-]', '', text)
                if normalized.startswith('8') and len(normalized) == 11:
                    normalized = '+7' + normalized[1:]
                elif normalized.isdigit():
                    normalized = '+' + normalized
                if not re.fullmatch(r'\+[1-9]\d{9,14}', normalized):
                    return screen('Проверьте номер: нужен код страны и 10–15 цифр. Например, +7 700 123 45 67.', [[button('← Назад', 'back')]])
                text = normalized
            bounds = {'name': (2, 80), 'phone': (11, 16), 'address': (10, 300), 'note': (1, 300)}
            low, high = bounds[field]
            if not low <= len(text) <= high or any(ord(ch) < 32 and ch not in '\n\t' for ch in text):
                return screen(f'Пожалуйста, введите от {low} до {high} символов.', [[button('← Назад', 'back'), button('Отмена', 'cancel_checkout')]])
            state['draft'][field] = text
            if field == 'note':
                return self.confirm_screen(state)
            state['step'] = {'name': 'phone', 'phone': 'address', 'address': 'note'}[field]
            return self.prompt(state)
        return self.home(state)

    def notify_staff(self, conn, order, title):
        for recipient in self.settings.admin_ids:
            for text in staff_order_messages(order, title):
                conn.execute(insert(outbox).values(target='admin', method='sendMessage',
                    payload={'chat_id': recipient, 'text': text, 'parse_mode': 'HTML'},
                    attempts=0, available_at=time.time(), sent=False, failed=False))

    def change_status(self, conn, order, status, notify=True):
        if status not in TRANSITIONS[order['status']]:
            raise ValueError('Недопустимый переход статуса')
        conn.execute(update(orders).where(orders.c.id == order['id']).values(status=status, updated_at=time.time()))
        conn.execute(insert(events).values(kind='order.status_changed', order_id=order['id'], payload={'status': status, 'version': 1}, created_at=time.time(), exported=False))
        if notify:
            self.enqueue(conn, order['route'], screen(f'<b>Заказ #{order["id"]}</b>\nНовый статус: {STATUSES[status]}.', [[button('Открыть заказ', f'order:{order["id"]}')]]))
