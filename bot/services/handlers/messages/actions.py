from db.models import Product, Product_image, Sale, Exclusive, Certificate
from ..callbacks.product import add_sale

from slugify import slugify
from io import BytesIO
from PIL import Image
from flask import current_app

from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase import pdfmetrics

from datetime import datetime, timezone

from reportlab.pdfgen import canvas
from reportlab.lib.colors import HexColor

from pathlib import Path

import traceback
import os

FIELDS = ["name", "price", "price_chet", "weight", "concept", "category", "descriptions", "G", "images"]
FIELDS_EXCLUSIVE = ["name", "price", "price_chet", "descriptions"]


ACTIONS = {
        "show": {
            "text": lambda ctx, msg, p:( f"{p.id}. G{p.G} {p.name} \nЗолото: {p.gold}/{p.form_gold}\nСеребро: {p.silver}/{p.form_silver}\n{p.price}₸ {ctx.users.get_material(msg=msg).upper()}"),
            "markup": lambda ctx, msg, p: (ctx.markup.change_count_product())
        },

        "change": {
            "text": lambda ctx, msg, p: (f"Выберите что хотите изменить у товара {ctx.fsm.get(msg.chat.id)['product_name']}"),
            "markup": lambda ctx, msg, p: (ctx.markup.change_product()),
        },
        "delete": {
            "text": lambda ctx, msg, p: (f"Вы уверены что хотите удалить товар {ctx.fsm.get(msg.chat.id)['product_name']}"),
            "markup": lambda ctx, msg, p: (ctx.markup.sure_delete())
        }
    }

TEXT_X_1 = 460
TEXT_Y_1 = 132
TEXT_X_2 = 322.5
TEXT_Y_2 = 83.5
TEXT_X_3 = 10
TEXT_Y_3 = 10

CURRENCY = "₸" #KZT
CUSTOM_PAGE_SIZE = (600, 300)


BASE_DIR = Path(__file__).resolve().parents[4]
FONT_PATH = BASE_DIR / "bot" / "static" / "fonts" / "ARIAL.TTF"
FRONT_PATH = BASE_DIR / "bot" / "static" / "images" / "front.jpg"
BACK_PATH = BASE_DIR / "bot" / "static" / "images" / "back.jpg"
CERTIFICATES_DIR = BASE_DIR / "certificates"


def action_with_product(ctx, msg, action):
    product = ctx.products.get_by_id(msg.text)

    if product is None:
        ctx.bot.send_message(
            chat_id=msg.chat.id,
            text="Некорректный ввод!",
            reply_markup=ctx.markup.back()
        )
        return
    
    ctx.fsm.set(msg.chat.id, {
        "state": "waitProduct",
        "product_id": product.id,
        "product_name": product.name,
    })

    text = ACTIONS[action]['text']
    markup = ACTIONS[action]['markup']

    ctx.bot.send_message(
        chat_id=msg.chat.id,
        text=text(ctx=ctx, msg=msg, p=product),
        reply_markup=markup(ctx=ctx, msg=msg, p=product),
    )


def change_product(ctx, msg):
    field = ctx.fsm.get(msg.chat.id)['field']

    product = ctx.products.get_by_id(ctx.fsm.get(msg.chat.id)['product_id'])

    if product is None:
        ctx.bot.send_message(
            chat_id=msg.chat.id,
            text=f"Ошибка изменения товара, товар не найден",
            reply_markup=ctx.markup.back()
        )
        return


    setattr(product, field, msg.text)

    ctx.db.session.commit()

    ctx.bot.send_message(
        chat_id=msg.chat.id,
        text=f"{field.capitalize()} {ctx.fsm.get(msg.chat.id)['product_name']} успешно обновлено на {msg.text}",
        reply_markup=ctx.markup.menu(role=ctx.users.get_role(msg=msg))
    )

    ctx.fsm.clear(msg.chat.id)


def add_product_field(ctx, msg):
    state = ctx.fsm.get(msg.chat.id)
    field = state['field']

    state['product'][field] = msg.text

    next_field = get_next_field(field, state, FIELDS)

    if next_field == "images":
        state['state'] = 'addProduct:images'


        ctx.bot.send_message(
            chat_id=msg.chat.id,
            text=f"Пришлите 4 {next_field}"
        )
        return
    
    if next_field:
        ctx.bot.send_message(
            chat_id=msg.chat.id,
            text=f"Введите {next_field}:"
        )
        return


def get_next_field(field, state, FIELDS):
    index = FIELDS.index(field)

    if index + 1 >= len(FIELDS):
        return None

    state['field'] = FIELDS[index + 1]

    return FIELDS[index + 1]


def add_product_images(ctx, msg):
    state = ctx.fsm.get(msg.chat.id)


    if not msg.photo:
        ctx.bot.send_message(
            msg.chat.id,
            "Нужно отправить фотографию"
        )
        return

    state['images'].append(msg.photo[-1].file_id)

    ctx.bot.send_message(
        msg.chat.id,
        f"Получено {len(state['images'])}/4"
    )

    if len(state['images']) < 4:
        ctx.fsm.set(msg.chat.id, state)
        return

    if state['state'] == 'addProduct:images':
        create_product(ctx, msg, state)
        return

    product = ctx.products.get_by_id(ctx.fsm.get(msg.chat.id)['product_id'])

    save_product_images(ctx, msg, state, product)


def create_product(ctx, msg, state):
    data = state["product"]
    

    product = Product(
        name=data["name"],
        price=int(data["price"]),
        price_chet=int(data["price_chet"]),
        weight=float(data["weight"]),
        concept=data["concept"],
        category=data["category"],
        descriptions=data["descriptions"],
        G=int(data["G"]),
        slug=slugify(data["name"]),
    )
    try:

        ctx.db.session.add(product)
        ctx.db.session.flush()


        save_product_images(ctx, msg, state, product)


        ctx.db.session.commit()
    except Exception as e:
        ctx.bot.send_message(
            msg.chat.id,
            e,
        )
        return

    ctx.bot.send_message(
        chat_id=msg.chat.id,
        text=f"Товар {product.name} успешно добавлен!",
        reply_markup=ctx.markup.back()
    )

    ctx.fsm.clear(msg.chat.id)



def save_product_images(ctx, msg, state, product):
    slug = slugify(product.name)

    base_path = product_images_path(product.slug)

    os.makedirs(base_path, exist_ok=True)

    for num, file_id in enumerate(state["images"], start=1):
        file_info = ctx.bot.get_file(file_id)
        file_data = ctx.bot.download_file(file_info.file_path)

        filename = f"img{num}.webp"
        filepath = os.path.join(base_path, filename)

        with open(filepath, "wb") as f:
            f.write(file_data)

        image = Product_image(
            num=num,
            product_id=product.id,
            img1=f"/static/image/productImgs/{slug}/{filename}"
        )

        pil_image = Image.open(BytesIO(file_data))
        pil_image.save(filepath, "WEBP")

        ctx.db.session.add(image)


    ctx.bot.send_message(
        chat_id=msg.chat.id,
        text=f"Фотографии для товара {product.name} успешно добавлены!"
    )



def product_images_path(slug):
    return os.path.join(
        current_app.static_folder or "",
        "image",
        "productImgs",
        slug
    )


def hide_product(ctx, msg):
    product=ctx.products.get_by_id(msg.text)

    if product.active:
        product.active=False

        ctx.bot.send_message(
            msg.chat.id,
            f"Товар {product.name} скрыт!",
            reply_markup=ctx.markup.menu(ctx.users.get_role(msg=msg))
        )

        ctx.db.session.commit()
        return
    product.active=True 

    ctx.bot.send_message(
        msg.chat.id,
        f"Товар {product.name} показан!",
        reply_markup=ctx.markup.menu(ctx.users.get_role(msg=msg))
    )
    ctx.db.session.commit()


def deposit_actions(ctx, msg):
    state = ctx.fsm.get(msg.chat.id)['action']

    if state == "delete":
        sale = ctx.db.session.query(Sale).filter_by(id = msg.text).first()

        ctx.db.session.delete(sale)
        ctx.db.session.commit()

        ctx.bot.send_message(
            chat_id=msg.chat.id,
            text=f"Запись {msg.text} успешно удалена!",
            reply_markup=ctx.markup.menu(ctx.users.get_role(msg=msg))
        )

    elif state == "period":
        start = msg.text.split(" ")[0]
        end = msg.text.split(" ")[1]

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

        ctx.bot.send_message(
            msg.chat.id,
            text,
            reply_markup=ctx.markup.back()
        )


def add_exclusive(ctx, msg):
    state = ctx.fsm.get(msg.chat.id)
    field = state['field']

    state['exclusive'][field] = msg.text

    next_field = get_next_field(field, state, FIELDS_EXCLUSIVE)

    if next_field:
        ctx.bot.send_message(
            msg.chat.id,
            f"Введите {next_field}"
        )
        return

    create_exclusive(ctx, msg, state)


def create_exclusive(ctx, msg, state):
    data = state["exclusive"]

    try:
        exclusive = Exclusive(
            name=data["name"],
            price=data["price"],
            price_chet=data["price_chet"],
            descriptions=data["descriptions"]
        )

        ctx.db.session.add(exclusive)
        ctx.db.session.commit()
        
        add_sale(ctx, exclusive, material=None, amount=1, exclusive_id=exclusive.id)
        
        ctx.bot.send_message(
            msg.chat.id,
            f"Эксклюзив {exclusive.name} был добавлен!",
            reply_markup=ctx.markup.menu(ctx.users.get_role(msg=msg))
        )
        

    except Exception as e:
        ctx.bot.send_message(
            msg.chat.id,
            f"Ошибка добавления exclusive: {e}"
        )

    ctx.fsm.clear(msg.chat.id)


def action_certificate(ctx, msg):
    action = ctx.fsm.get(msg.chat.id)["action"]

    if action == 'add':
        amount = msg.text

        try:
            cert = Certificate(amount=amount)

            ctx.db.session.add(cert)
            ctx.db.session.commit()

            num = cert.id

            pdf_path = create_certificate_pdf(num, amount)

            with open(pdf_path, "rb") as file:
                ctx.bot.send_document(msg.chat.id, file)

        except Exception as e:
            ctx.bot.send_message(msg.chat.id, f"{e} {traceback.format_exc()}")

    elif action == 'activate':
        try:
            cert = ctx.db.session.query(Certificate).filter_by(id = msg.text).first()
            if cert.user_at is None:
                cert.user_at = datetime.now(timezone.utc).date()

                ctx.db.session.commit()

                ctx.bot.send_message(msg.chat.id, f"Сертификат №{msg.text}\nНа сумму {cert.amount}\nУспешно активирован {datetime.now(timezone.utc).date()}", reply_markup=ctx.markup.menu(ctx.users.get_role(msg=msg)))
            else:
                ctx.bot.send_message(msg.chat.id, f"❌ОШИБКА!\nСертификат №{msg.text}\nНа сумму {cert.amount}\nУже был активирован {datetime.now(timezone.utc).date()}", reply_markup=ctx.markup.menu(ctx.users.get_role(msg=msg)))

        except Exception as e:
            ctx.db.session.rollback()
            ctx.bot.send_message(msg.chat.id, f"{e} {traceback.format_exc()}")



def create_certificate_pdf(num, amount):
    
    pdfmetrics.registerFont(TTFont('Arial', str(FONT_PATH)))

    
    time = f"Выдан: {datetime.today().day}.{datetime.today().strftime('%m')}.{datetime.today().year}"
    

    output_filename = f"Сертификат KoDee Desire №{num}-{amount}.pdf"
    
    pdf_path = CERTIFICATES_DIR / output_filename
    
    pdf = canvas.Canvas(str(pdf_path), pagesize=CUSTOM_PAGE_SIZE)
    
    if os.path.exists(FRONT_PATH):
        pdf.drawInlineImage(str(FRONT_PATH), 0, 0, width=CUSTOM_PAGE_SIZE[0], height=CUSTOM_PAGE_SIZE[1])
    else:
        print("no front")

    pdf.setFont("Arial", 23)
    pdf.setFillColor(HexColor("#000000"))
    pdf.drawString(TEXT_X_1, TEXT_Y_1, f"{num}")  # номер
    pdf.setFont("Arial", 17)
    pdf.drawString(TEXT_X_2, TEXT_Y_2, f"{amount} {CURRENCY}")  # сумма

    pdf.showPage()
    if os.path.exists(BACK_PATH):
        pdf.drawInlineImage(str(BACK_PATH), 0, 0, width=CUSTOM_PAGE_SIZE[0], height=CUSTOM_PAGE_SIZE[1])

    pdf.setFont("Arial", 12)
    pdf.drawString(TEXT_X_3, TEXT_Y_3, time)  # Дата

    pdf.save()
        
    return pdf_path