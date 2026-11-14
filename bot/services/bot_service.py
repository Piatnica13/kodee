from ..context import BotContext

from .handlers.callbacks.other import material, role, notify, product_action, exclusive, deposit, certificate
from .handlers.callbacks.menu import menu
from .handlers.callbacks.change_count import count, count_msg
from .handlers.callbacks.catalog import callback_catalog
from .handlers.messages.actions import action_with_product, change_product, add_product_field, add_product_images, hide_product, deposit_actions, add_exclusive, action_certificate
from telebot.apihelper import ApiTelegramException

from .handlers.utils import incorrect_input
from .access import allowed


CALLBACK_ROUTES = {
    "menu": menu,
    "catalog": callback_catalog,
    "count": count,
    "material": material,
    "role": role,
    "notify": notify,
    "product_action": product_action,
    "exclusive": exclusive,
    "deposit": deposit,
    "certificate": certificate
}

MESSAGE_ROUTES = {
    "waitProduct": "show",
    "changeProduct": "change",
    "deleteProduct": "delete",

    "waitCount": count_msg,
    "waitDeposit": deposit_actions,
    "waitExclusive": add_exclusive,
    "waitCertificate": action_certificate,

    "hideProduct": hide_product,
    "waitChange": change_product,
    "addProduct": add_product_field
}


class BotService:
    def __init__(self, bot, app, db, fsm, markup, user, ps, notification):
        self.ctx = BotContext(bot=bot, app=app, db=db, fsm=fsm, markup=markup, users=user, products=ps, notifications=notification) # type: ignore


    def check_callbacks(self, call):
        if not allowed(call.message, call.from_user):
            return
        if not isinstance(call.data, str) or len(call.data) > 64:
            raise ValueError("Некорректная команда")
        try:
            action = call.data.split(":")[0]
            handler = CALLBACK_ROUTES.get(action)

            if handler:
                handler(self.ctx, call)

        except ApiTelegramException as e:
            if "message is not modified" in str(e):
                return
            raise


    def check_text_msg(self, msg):
        if not allowed(msg):
            return
        state = self.ctx.fsm.get(msg.chat.id)

        if not state:
            incorrect_input(ctx=self.ctx, msg=msg)
            return

        route = MESSAGE_ROUTES.get(state["state"])

        if route is None:
            incorrect_input(ctx=self.ctx, msg=msg)
            return

        if callable(route):
            return route(ctx=self.ctx, msg=msg)

        action_with_product(self.ctx, msg, route)



    def check_image(self, msg):
        if not allowed(msg):
            return
        state = self.ctx.fsm.get(msg.chat.id)

        if not state or state.get('state') not in {'addProduct:images', 'waitChange:images'}:
            incorrect_input(ctx=self.ctx, msg=msg)
            return

        if not state.get('images'):
            state['images'] = []

        add_product_images(self.ctx, msg) # if state['state'] == "addProduct:images":# if state['state'] == 'changeProduct:images':
