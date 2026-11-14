from .product import add_sale
from web.app.log import log_action


def count(ctx, call):
    material = ctx.users.get_material(call=call)
    product_id = ctx.fsm.get(call.message.chat.id)['product_id']

    _, value = call.data.split(":")

    if value == 'your':
        ctx.fsm.set(call.message.chat.id, {
            'product_id': product_id,
            'state': 'waitCount'
        })
        ctx.bot.send_message(
            chat_id=call.message.chat.id,
            text="Введите свое число",
            reply_markup=ctx.markup.back()
        )
        return

    amount = int(value)

    result = _change_product_count_core(
        ctx=ctx,
        product_id=product_id,
        material=material,
        amount=amount
    )

    ctx.bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text=result['text'],
        reply_markup=result['markup']
    )


def count_msg(ctx, msg):
    material = ctx.users.get_material(msg=msg)

    product_id = ctx.fsm.get(msg.chat.id)['product_id']
    try:
        amount = int(msg.text)
    except ValueError:
        raise ValueError("Enter is not correct")


    result = _change_product_count_core(ctx=ctx, product_id=product_id, material=material, amount=amount)

    ctx.bot.send_message(
        chat_id=msg.chat.id,
        text=result['text'],
        reply_markup=result['markup'])

    ctx.fsm.set(msg.chat.id, {
        "state": "waitProduct",
        "product_id": result['product_id']
    })


def _change_product_count_core(ctx, product_id, material, amount):
    from sqlalchemy import update
    from db.models import Product
    from web.app.validation import STOCK_FIELDS, positive_id
    if material not in STOCK_FIELDS or type(amount) is not int or not -1000000 <= amount <= 1000000 or amount == 0:
        raise ValueError('Недопустимое изменение остатка')
    product_id = positive_id(product_id)
    column = getattr(Product, material)
    try:
        result = ctx.db.session.execute(update(Product).where(
            Product.id == product_id, column + amount >= 0
        ).values({material: column + amount}).execution_options(synchronize_session=False))
        if result.rowcount != 1:
            raise ValueError('Товар не найден или недостаточно остатка')
        product = ctx.db.session.get(Product, product_id, populate_existing=True)
        if amount < 0 and material in {'gold', 'silver'}:
            add_sale(ctx, product, material, amount, product_id=product.id)
        ctx.db.session.commit()
    except Exception:
        ctx.db.session.rollback()
        raise
    log_action('product.stock_changed', source='telegram', entity_id=product_id, material=material, amount=amount)
    text = f"{product.id}. G{product.G} {product.name} \nЗолото: {product.gold}/{product.form_gold}\nСеребро: {product.silver}/{product.form_silver}\n{product.price}₸ {material.upper()}"
    return {'markup': ctx.markup.change_count_product(), 'text': text, 'product_id': product_id}
