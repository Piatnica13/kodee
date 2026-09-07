from ..utils import dispatch
from .product import change_call, add_product, change_call_images, delete_product
from .catalog import show_catalog
from db.models import Sale, Certificate

from datetime import timedelta


PRODUCT_ACTIONS = {
    "change": "changeProduct",
    "hide": "hideProduct",
    "delete": "deleteProduct",
}


def product_action(ctx, call):

    parts = call.data.split(":")

    if len(parts) == 1:
        return ctx.bot.edit_message_text(
            text="Выберите действие",
            message_id=call.message.message_id,
            chat_id=call.message.chat.id,
            reply_markup=ctx.markup.product_function()
        )

    action = parts[1]

    if len(parts) == 2:

        state, _ = dispatch(ctx, call, PRODUCT_ACTIONS, 1)

        if state:
            return show_catalog(
                ctx,
                call.message.chat.id,
                call.message.message_id,
                state
            )
        
    if action == 'change':
        field = call.data.split(":")[2] 
        if field == 'images':
            change_call_images(ctx, call)
            return
        change_call(ctx, call, field=field)

    elif action == 'add':
        add_product(ctx, call)

    elif action == 'delete':
        delete_product(ctx, call)


def material(ctx, call):
    material = call.data.split(":")[1]

    ctx.users.change_material(material, call.message)

    product = ctx.products.get_by_id_or_name(ctx.fsm.get(call.message.chat.id)['product_id'])

    ctx.bot.edit_message_text(chat_id=call.message.chat.id, text=f"{product.id}. G{product.G} {product.name} \nЗолото: {product.gold}/{product.form_gold}\nСеребро: {product.silver}/{product.form_silver}\n{product.price}₸ {ctx.users.get_material(msg=call.message).upper()}", reply_markup=ctx.markup.change_count_product(), message_id=call.message.message_id) # type: ignore


def role(ctx, call):
    parts = call.data.split(":")

    if len(parts) == 1:
        ctx.bot.edit_message_text(
            text=f"Ваша роль: {ctx.users.get_role(call=call)}\nВыберите роль:",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=ctx.markup.role()
        )
    else:
        user = ctx.users.change_user_role(parts[1], call.message)

        ctx.bot.edit_message_text(
            text=f"Ваша роль - {user.role}!",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=ctx.markup.menu(role=ctx.users.get_role(call=call))
        )


def exclusive(ctx, call):
    ctx.fsm.set(call.message.chat.id, {
        "state": "waitExclusive",
        "field": "name",
        "exclusive": {}
    })


    return ctx.bot.edit_message_text(
        text=f"Введите название эксклюзива:",
        message_id=call.message.message_id,
        chat_id=call.message.chat.id,
        reply_markup=ctx.markup.back(),
    )


def notify(ctx, call):
    ctx.notifications.notify_workers(ctx=ctx, call=call)



def deposit(ctx, call):
    action = call.data.split(":")

    # deposit:delete
    if len(action) == 2 and action[1] == "delete":
        ctx.fsm.set(call.message.chat.id, {
            "state": "waitDeposit",
            "action": "delete"
        })

        records = ctx.db.session.query(Sale).all()

        text = "Введите ID записи:\n"

        for record in records:
            text += (
                f"{record.id}. {record.name} "
                f"{record.quantity}шт {record.material}\n"
                f"{record.price * record.quantity}тг "
                f"{record.price_chet * record.quantity}тг\n"
                f"{record.sold_at}\n\n"
            )

        return ctx.bot.edit_message_text(
            text=text,
            message_id=call.message.message_id,
            chat_id=call.message.chat.id,
            reply_markup=ctx.markup.back()
        )

    # deposit:period
    if len(action) == 2 and action[1] == "period":
        ctx.fsm.set(call.message.chat.id, {
            "state": "waitPeriodStart",
            "date": {
                "start": {},
                "end": {}
            }
        })

        return ctx.bot.edit_message_text(
            text="Выберите год начала периода",
            message_id=call.message.message_id,
            chat_id=call.message.chat.id,
            reply_markup=ctx.markup.years("start")
        )

    # deposit:period:start/end:year/month/day:value
    if len(action) == 5 and action[1] == "period":
        period_type = action[2]   # start / end
        date_type = action[3]     # year / month / day
        value = action[4]

        data = ctx.fsm.get(call.message.chat.id)

        # Защита от некорректного callback
        if not data or "date" not in data:
            return

        date = data["date"][period_type]

        date[date_type] = value

        # Выбрали год
        if date_type == "year":
            text = (
                "Выберите месяц "
                + ("начала" if period_type == "start" else "конца")
                + " периода"
            )

            markup = ctx.markup.months(period_type)

        # Выбрали месяц
        elif date_type == "month":
            text = (
                "Выберите день "
                + ("начала" if period_type == "start" else "конца")
                + " периода"
            )

            markup = ctx.markup.days(
                period_type,
                date["year"],
                date["month"]
            )

        # Выбрали день
        elif date_type == "day":

            if period_type == "start":
                data["state"] = "waitPeriodEnd"

                text = "Выберите год конца периода"
                markup = ctx.markup.years("end")

            else:
                data["state"] = "periodReady"

                start = f"{data['date']['start']['year']}.{data['date']['start']['month']}.{data['date']['start']['day']}"
                end = f"{data['date']['end']['year']}.{data['date']['end']['month']}.{data['date']['end']['day']}"

                records = ctx.db.session.query(Sale).filter(
                    Sale.sold_at >= start,
                    Sale.sold_at <= end
                ).all()
        
                text = ''
                count_gold=0
                count_silver=0
                count_exclusive = 0
        
                for index, record in enumerate(records, start=1):
                    count_gold += record.quantity if record.material == 'gold' else 0
                    count_silver += record.quantity if record.material == 'silver' else 0
                    count_exclusive += 1 if record.exclusive_id is not None else 0
        
                    text += (f"{index}. {record.name} {record.quantity}шт {record.material}\n{record.price * record.quantity}тг {record.price_chet * record.quantity}тг\n{record.sold_at}\n\n")
        
                text += f"\nПериод: {start}-{end}\nЗолото: {count_gold}\nСеребро: {count_silver}\nЭксклюзивов: {count_exclusive}\nЦена: {sum(record.price * record.quantity for record in records)}\nДепозит: {sum(record.price_chet * record.quantity for record in records)}"
                
                markup = ctx.markup.back()

        else:
            return

        ctx.fsm.set(call.message.chat.id, data)

        return ctx.bot.edit_message_text(
            text=text,
            message_id=call.message.message_id,
            chat_id=call.message.chat.id,
            reply_markup=markup
        )

    return ctx.bot.edit_message_text( text="Выберите действие", message_id = call.message.message_id, chat_id = call.message.chat.id, reply_markup=ctx.markup.deposit())


def certificate(ctx, call):
    action = call.data.split(":")

    if len(action) == 2 and action[1] == "add":
        ctx.fsm.set(call.message.chat.id, {
                "state": "waitCertificate",
                "action": "add"
            })
        
        ctx.bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                reply_markup=ctx.markup.back(),
                text=f"Введите сумму сертификата: "
            )
        
        return
    elif len(action) == 2 and action[1] == "show":
        certificates = ctx.db.session.query(Certificate).all()
        text = ''

        for certificate in certificates:
            if certificate.user_at is None:
                text += f"Сертификат №{certificate.id}\nСумма: {certificate.amount}\nВыдан: {certificate.created_at}\nДействует до: {certificate.created_at + timedelta(days=60)}\n\n"
            else:
                text += f"Сертификат №{certificate.id}\nСумма: {certificate.amount}\nВыдан: {certificate.created_at}\nИспользован: {certificate.user_at}\n\n"

        ctx.bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=text,
            reply_markup=ctx.markup.back(),
        )

        return
    elif len(action) == 2 and action[1] == "activate":
        ctx.fsm.set(call.message.chat.id, {
            "state": "waitCertificate",
            "action": "activate"
        })

        ctx.bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=f"Введите номер сертификата: ",
            reply_markup=ctx.markup.back(),
        )
        return

    

    ctx.bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=ctx.markup.certificate(),
            text=f"Выберите действие"
        )