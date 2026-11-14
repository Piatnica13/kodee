from db.models import User, Product
from flask import current_app

class NotificationService:
    def notify_workers(self, ctx, call):
        CRITICAL_LIMIT = 3
        workers = User.query.filter(User.role == "worker", User.telegram_id.in_(current_app.config.get("BOT_ALLOWED_USER_IDS", set()))).all()
        critical_products = Product.query.filter(Product.gold <= CRITICAL_LIMIT).all() # type: ignore
        if not workers or not critical_products:
            return

        text=NotificationService._build_message(critical_products) # type: ignore

        for worker in workers:
            ctx.bot.send_message(chat_id=worker.telegram_id, text=text)

    @staticmethod
    def _build_message(products):
        result = ['Заканчиваются товары:\n']
        for product in products:
            result.append(
                f"• {product.name}\nЗолото: {product.gold}/{product.form_gold}\nСеребро: {product.silver}/{product.form_silver}\n"
            )

        return "\n".join(result)
