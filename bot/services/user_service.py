from db.models import User, db
from .access import allowed
from web.app.validation import STOCK_FIELDS
from flask import current_app
from web.app.log import log_action


class UserService:
    def reg(self, msg):
        if not allowed(msg):
            raise ValueError("Доступ к боту закрыт")
        telegram_id = msg.from_user.id

        user = User.query.filter_by(telegram_id=telegram_id).first()

        created = user is None
        if not user:
            try:
                user = User(
                    name=(msg.from_user.first_name or msg.from_user.username or '')[:25],
                    last_name=(msg.from_user.last_name or '')[:40],
                    user_name=msg.from_user.username or '',
                    first_name=msg.from_user.first_name or '',
                    telegram_id=telegram_id,
                    role='seller'
                ) # type: ignore
                db.session.add(user)
            except Exception as e:
                current_app.logger.exception("Не удалось зарегистрировать пользователя бота")
                db.session.rollback()
                raise
        elif msg.from_user.is_bot == False:
            user.user_name = msg.from_user.username
            user.first_name = msg.from_user.first_name

        db.session.commit()
        if created:
            log_action('registration', source='telegram', entity_id=user.id)
        return user


    def get_user(self, call):
        return User.query.filter_by(telegram_id=call.message.chat.id).first()



    def change_user_role(self, role, msg):
        if role not in {"seller", "worker"}:
            raise ValueError("Недопустимая роль")
        user = User.query.filter_by(telegram_id=msg.chat.id).first()

        if user is not None:
            user.role = role

        db.session.commit()
        if user is not None:
            log_action('user.role_changed', source='telegram', entity_id=user.id, role=role)
        return user


    def get_role(self, msg=None, call=None):
        if msg is not None:
            telegram_id = msg.chat.id
        elif call is not None:
            telegram_id = call.message.chat.id
        else:
            telegram_id = None

        user = User.query.filter_by(telegram_id=telegram_id).first()

        if user is not None:
            return user.role
        return "None"


    def change_material(self, material, msg):
        if material not in STOCK_FIELDS:
            raise ValueError("Недопустимый материал")
        try:
            user = User.query.filter_by(telegram_id=msg.chat.id).first()

            if user is not None:
                user.material = material

            db.session.commit()
            if user is not None:
                log_action('user.material_changed', source='telegram', entity_id=user.id, material=material)

            return user

        except Exception as e:
            current_app.logger.exception("Ошибка смены материала")
            db.session.rollback()
            raise


    def get_material(self, msg=None, call=None):
        if msg is not None:
            telegram_id = msg.chat.id
        elif call is not None:
            telegram_id = call.message.chat.id
        else:
            telegram_id = None

        user = User.query.filter_by(telegram_id=telegram_id).first()

        if user is not None:
            return user.material
