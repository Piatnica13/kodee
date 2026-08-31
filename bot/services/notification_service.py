from db.models import User, Product

class NotificationService:
    def notify_workers(self, ctx, call):
        CRITICAL_LIMIT = 3
        workers = User.query.filter_by(role="worker").all()
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