"""Order management available only to configured staff of the private bot."""
import re
from flask import current_app
from sqlalchemy import select
from web.app.log import log_action
from .dialog import STATUSES, TRANSITIONS, money, staff_order_messages
from .storage import orders


def handle_order_command(bot, message):
    actor = message.from_user.id
    if actor not in current_app.config['CUSTOMER_BOT_ADMIN_IDS']:
        bot.send_message(message.chat.id, 'Доступ к заявкам не настроен.')
        return
    parts = (message.text or '').split()
    command = parts[0].split('@', 1)[0]
    dialog = current_app.extensions['customer_bot']
    if command == '/orders':
        with dialog.store.transaction() as conn:
            rows = conn.execute(select(orders).where(orders.c.status.notin_(['completed', 'cancelled']))
                                .order_by(orders.c.created_at.desc()).limit(20)).mappings().all()
        text = 'Активные заявки:\n' + '\n'.join(
            f'#{row["id"]} · {STATUSES[row["status"]]} · {money(row["total"])}' for row in rows) if rows else 'Активных заявок нет.'
        bot.send_message(message.chat.id, text + '\n\nПодробнее: /order НОМЕР')
        return
    if len(parts) < 2 or not re.fullmatch(r'(?:[A-Fa-f0-9]{8}|[A-Fa-f0-9]{16})', parts[1]):
        bot.send_message(message.chat.id, 'Используйте /order НОМЕР или /order_status НОМЕР СТАТУС.')
        return
    oid = parts[1].upper()
    changed = None
    with dialog.store.transaction() as conn:
        order = conn.execute(select(orders).where(orders.c.id == oid)).mappings().first()
        if not order:
            response = 'Заявка не найдена.'
        elif command == '/order_status':
            status = parts[2].lower() if len(parts) == 3 else ''
            if status not in TRANSITIONS[order['status']]:
                available = ', '.join(sorted(TRANSITIONS[order['status']])) or 'нет'
                response = f'Недопустимый статус. Доступные переходы: {available}.'
            else:
                dialog.change_status(conn, order, status)
                changed = status
                response = f'Заявка #{oid}: {STATUSES[status]}. Уведомление покупателю поставлено в очередь.'
        else:
            response = staff_order_messages(order, f'Заявка · {STATUSES[order["status"]]}')
            response.append(f'Статус: /order_status {oid} confirmed|preparing|shipped|completed|cancelled')

    if changed:
        log_action('order.status_changed', actor_id=actor, source='telegram', entity_id=oid, status=changed)
    for part in response if isinstance(response, list) else [response]:
        bot.send_message(message.chat.id, part, parse_mode='HTML')
