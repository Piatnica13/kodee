from telebot import types
from datetime import datetime
import calendar


class MarkupService:
    def menu(self, role):
        markup = types.InlineKeyboardMarkup(row_width=1)
        btn1 = types.InlineKeyboardButton("Количество товаров", callback_data="catalog")
        btn2 = types.InlineKeyboardButton("Действия с товарами", callback_data="product_action")
        btn3 = types.InlineKeyboardButton("Добавить эксклюзив", callback_data="exclusive")
        btn4 = types.InlineKeyboardButton("Депозит", callback_data="deposit")
        btn7 = types.InlineKeyboardButton("Сертификат", callback_data="certificate")
        btn5 = types.InlineKeyboardButton("Роль", callback_data="role")
        if role == "seller":
            btn6 = types.InlineKeyboardButton("Оповестить рабочих", callback_data="notify")
            markup.add(btn1, btn2, btn3, btn4, btn7, btn5, btn6)
        else:
            markup.add(btn1, btn2, btn3, btn4, btn7, btn5)
        
        return markup


    def product_function(self):
        markup = types.InlineKeyboardMarkup(row_width=1)
        btn1 = types.InlineKeyboardButton("Добавить товар", callback_data="product_action:add")
        btn2 = types.InlineKeyboardButton("Изменить товар", callback_data="product_action:change")
        btn3 = types.InlineKeyboardButton("Скрыть товар", callback_data="product_action:hide")
        btn4 = types.InlineKeyboardButton("Удалить товар", callback_data="product_action:delete")
        btn5 = types.InlineKeyboardButton("⬅️Меню", callback_data='menu')
        markup.add(btn1, btn2, btn3, btn4, btn5)

        return markup
    
        
    def change_product(self):
        markup = types.InlineKeyboardMarkup(row_width=2)
        
        btn1 = types.InlineKeyboardButton("Название", callback_data='product_action:change:name')
        btn11 = types.InlineKeyboardButton("Короткое название", callback_data='product_action:change:short_name')
        btn2 = types.InlineKeyboardButton("Цена", callback_data='product_action:change:price')
        btn3 = types.InlineKeyboardButton("Цена депозита", callback_data='product_action:change:price_chet')
        btn4 = types.InlineKeyboardButton("Вес", callback_data='product_action:change:weight')
        btn5 = types.InlineKeyboardButton("Концепт", callback_data='product_action:change:concept')
        btn6 = types.InlineKeyboardButton("Категория", callback_data='product_action:change:category')
        btn7 = types.InlineKeyboardButton("Описание", callback_data='product_action:change:descriptions')
        btn8 = types.InlineKeyboardButton("G", callback_data='product_action:change:G')
        btn9 = types.InlineKeyboardButton("Фотографии", callback_data='product_action:change:images')
        btn10 = types.InlineKeyboardButton("⬅️Меню", callback_data='menu')
                
        markup.add(btn1, btn11, btn2, btn3, btn4, btn5, btn6, btn7, btn8, btn9, btn10)
        
        return markup
    

    def change_count_product(self):
        markup = types.InlineKeyboardMarkup(row_width=2)
        
        btn1 = types.InlineKeyboardButton("-1 (Продать)", callback_data=f'count:-1')
        btn2 = types.InlineKeyboardButton("+1 (Пополнить)", callback_data=f'count:1')
        btn3 = types.InlineKeyboardButton("⬅️Меню", callback_data='menu')
        btn4 = types.InlineKeyboardButton("Свое число", callback_data=f'count:your')
        btn5 = types.InlineKeyboardButton("Золото", callback_data='material:gold')
        btn6 = types.InlineKeyboardButton("Серебро", callback_data='material:silver')
        btn7 = types.InlineKeyboardButton("З. заготовки", callback_data='material:form_gold')
        btn8 = types.InlineKeyboardButton("С. заготовки", callback_data='material:form_silver')
                
        markup.add(btn2, btn1, btn5, btn6, btn7, btn8, btn3, btn4)
        
        return markup

    

    def back(self):
        markup = types.InlineKeyboardMarkup(row_width=1)

        btn1 = types.InlineKeyboardButton("⬅️Меню", callback_data="menu")

        markup.add(btn1)

        return markup


    def sure_delete(self):
        markup = types.InlineKeyboardMarkup(row_width=1)
        
        btn1 = types.InlineKeyboardButton("✅Да", callback_data="product_action:delete:yes")
        btn2 = types.InlineKeyboardButton("❌Нет", callback_data="menu")

        markup.add(btn1, btn2)

        return markup
        
    
    
    def role(self):
        markup = types.InlineKeyboardMarkup(row_width=1)
        
        btn1 = types.InlineKeyboardButton("Продовец", callback_data="role:seller")
        btn2 = types.InlineKeyboardButton("Рабочий", callback_data="role:worker")
        btn3 = types.InlineKeyboardButton("⬅️Меню", callback_data="menu")
        
        markup.add(btn1, btn2, btn3)
        
        return markup


    def deposit(self):
        markup = types.InlineKeyboardMarkup(row_width=1)

        btn1 = types.InlineKeyboardButton("Выбрать период расчета", callback_data="deposit:period")
        btn2 = types.InlineKeyboardButton("Удалить запись", callback_data="deposit:delete")

        markup.add(btn1, btn2)

        return markup


    def certificate(self):
        markup = types.InlineKeyboardMarkup(row_width=1)

        btn1 = types.InlineKeyboardButton("Создать", callback_data="certificate:add")
        btn2 = types.InlineKeyboardButton("Посмотреть", callback_data="certificate:show")
        btn3 = types.InlineKeyboardButton("Активировать", callback_data="certificate:activate")

        markup.add(btn1, btn2, btn3)       

        return markup 


    def years(self, period_type):
        markup = types.InlineKeyboardMarkup(row_width=3)

        year = datetime.now().year

        btn1 = types.InlineKeyboardButton(f"{year - 1}", callback_data=f"deposit:period:{period_type}:year:{year - 1}")
        btn2 = types.InlineKeyboardButton(f"{year}", callback_data=f"deposit:period:{period_type}:year:{year}")
        btn3 = types.InlineKeyboardButton(f"{year + 1}", callback_data=f"deposit:period:{period_type}:year:{year + 1}")

        markup.add(btn1, btn2, btn3)

        return markup


    def months(self, period_type):
        months = [
            'Январь', 'Февраль', 'Март', 'Апрель',
            'Май', 'Июнь', 'Июль', 'Август',
            'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь'
        ]

        markup = types.InlineKeyboardMarkup()

        buttons = []

        for index, month in enumerate(months, start=1):
            buttons.append(
                types.InlineKeyboardButton(
                    month,
                    callback_data=f"deposit:period:{period_type}:month:{index}"
                )
            )

        for i in range(0, len(buttons), 4):
            markup.row(*buttons[i:i + 4])

        return markup


    def days(self, period_type, year, month):
        markup = types.InlineKeyboardMarkup(row_width=2)

        days_count = calendar.monthrange(
            int(year),
            int(month)
        )[1]

        buttons = []

        for day in range(1, days_count + 1):
            buttons.append(
                types.InlineKeyboardButton(
                    str(day),
                    callback_data=f"deposit:period:{period_type}:day:{day}"
                )
            )

        for i in range(0, len(buttons), 4):
            markup.row(*buttons[i:i + 4])

        return markup