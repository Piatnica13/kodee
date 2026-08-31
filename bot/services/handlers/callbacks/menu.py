def menu(ctx, call):
    show_menu(ctx, ctx.users.get_role(msg=call.message), call.message.chat.id, call.message.message_id)


def start_menu(ctx, msg):
    show_menu(ctx, ctx.users.get_role(msg=msg), msg.chat.id)


def show_menu(ctx, role, chat_id, message_id=None):
    ctx.fsm.set(chat_id, {
        'state': "waitSelected"
    })

    if message_id:
        ctx.bot.edit_message_text(
            text="Выберите действие:",
            chat_id=chat_id,
            message_id=message_id,
            reply_markup=ctx.markup.menu(role)
        )
    else:
        ctx.bot.send_message(
            chat_id=chat_id,
            text="Выберите действие:",
            reply_markup=ctx.markup.menu(role)
        )