def dispatch(ctx, call, routes, level):
    parts = call.data.split(":")

    value = routes.get(parts[level])

    if callable(value):
        return value(ctx, call)

    return value, parts[level]


def incorrect_input(ctx, msg):
    return ctx.bot.send_message(
        chat_id=msg.chat.id,
        text="Некорректный ввод!",
        reply_markup=ctx.markup.back()
    )