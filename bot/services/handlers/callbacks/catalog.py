def show_catalog(ctx, chat_id, message_id, state):
    with ctx.app.app_context():
        products = ctx.products.get_all()

    result = ''
    count = 1
    
    for i in products:
        result += f"{count}. ID:{i.id}. {i.name} {i.gold}/{i.silver}\n"
        count += 1
    
    ctx.bot.edit_message_text(
        text=result,
        chat_id=chat_id,
        message_id=message_id
    )
    ctx.bot.send_message(
        chat_id=chat_id,
        text="Введите ID браслета: ",
        reply_markup=ctx.markup.back()
    )
    ctx.fsm.set(chat_id, {
        "state": state
    })


def catalog(ctx, msg):
    show_catalog(ctx, msg.chat.id, msg.message_id, "waitProduct")


def callback_catalog(ctx, call):
    show_catalog(ctx, call.message.chat.id, call.message.message_id, "waitProduct")

