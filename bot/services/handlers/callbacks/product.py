from db.models import Sale

def change_call(ctx, call, field):
    ctx.fsm.set(call.message.chat.id, {
        "state": "waitChange",
        "field": field,
        "product_id": ctx.fsm.get(call.message.chat.id)['product_id'],
        "product_name": ctx.fsm.get(call.message.chat.id)['product_name']
    })
    
    ctx.bot.edit_message_text(
        text=f"Введите новую {field} для товара {ctx.fsm.get(call.message.chat.id)['product_name']}",
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        reply_markup=ctx.markup.back()
    )


def change_call_images(ctx, call):
    ctx.fsm.set(call.message.chat.id, {
        "state": "waitChange:images",
        "field": "images",
        "product_id": ctx.fsm.get(call.message.chat.id)['product_id'],
        "product_name": ctx.fsm.get(call.message.chat.id)['product_name']
    })
    
    ctx.bot.edit_message_text(
        text=f"Пришлите 4 фотографии для товара {ctx.fsm.get(call.message.chat.id)['product_name']}",
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        reply_markup=ctx.markup.back()
    )


def add_product(ctx, call):
    ctx.fsm.set(call.message.chat.id, {
        "state": "addProduct",
        "field": "name",
        "product": {}
    })


    ctx.bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text=f"Введите название нового продукта:",
        reply_markup=ctx.markup.back(),
    )


def delete_product(ctx, call):
    product_id = ctx.fsm.get(call.message.chat.id)['product_id']
    product = ctx.products.get_by_id(product_id)

    ctx.db.session.delete(product)
    ctx.db.session.commit()

    ctx.bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text=f"Товар успешно удален!",
        reply_markup=ctx.markup.menu(role=ctx.users.get_role(call=call)),
    )



def add_sale(ctx, product, material, amount, product_id=None, exclusive_id=None):

    try:
        sale = Sale(
            product_id=product_id,
            exclusive_id=exclusive_id,
            name=product.name,
            price=product.price,
            price_chet=product.price_chet,
            quantity=abs(amount),
            material=material
            )

        ctx.db.session.add(sale)
        ctx.db.session.commit()
    except Exception as e:
        print("Не получилось добавить товар в проданные: ", e)


