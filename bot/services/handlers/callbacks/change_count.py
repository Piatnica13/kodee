from .product import add_sale


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

    product = ctx.products.get_by_id_or_name(product_id)
        
    current_count = getattr(product, material)
    setattr(product, material, current_count + amount)

    ctx.db.session.commit()

    if amount < 0 and material != 'form_gold' and material != 'form_silver':
        add_sale(ctx, product, material, amount, product_id=product.id)

    text = f"{product.id}. G{product.G} {product.name} \nЗолото: {product.gold}/{product.form_gold}\nСеребро: {product.silver}/{product.form_silver}\n{product.price}₸ {material.upper()}" # type: ignore
    markup = ctx.markup.change_count_product()

    return {'markup': markup, 'text': text, 'product_id': product_id}