from db.models import User, Address, db
from flask import session, current_app, request, flash
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from web.app.validation import text, email as valid_email
from web.app.security import establish_session
from web.app.log import log_action
import os


class UserService:
    @staticmethod
    def get_user(user_id):
        if not isinstance(user_id, int) or isinstance(user_id, bool):
            return None
        return db.session.get(User, user_id)

    @staticmethod
    def update_user(user, data):
        name = text(data.get('name', ''), 'Имя', 25)
        last_name = text(data.get('last_name', ''), 'Фамилия', 40, False)
        phone = text(data.get('phone', ''), 'Телефон', 11, False)
        address = text(data.get('address', user.address or ''), 'Адрес', 150, False)
        if phone and (not phone.isdigit() or len(phone) != 11):
            raise ValueError('Телефон должен содержать 11 цифр')
        submitted_email = data.get('email', user.email or '')
        email = valid_email(submitted_email) if submitted_email else user.email
        if email != user.email:
            if not email:
                raise ValueError('Укажите Email')
            reserved = current_app.config.get('ADMIN_EMAIL', '').strip().lower()
            if email == reserved or User.query.filter(func.lower(User.email) == email, User.id != user.id).first():
                raise ValueError('Этот Email уже используется')
            session.pop('admin', None)
            user.email = email
        user.name, user.last_name, user.phone, user.address = name, last_name, phone, address
        flash('Информация о пользователе успешно обновлена.')

    @staticmethod
    def update_password(user, data):
        password = data.get('newPass', '')
        if not isinstance(password, str) or not 6 <= len(password) <= 128 or password != data.get('reNewPass'):
            raise ValueError('Пароли должны совпадать и содержать от 6 до 128 символов')
        user.password = generate_password_hash(password)
        flash('Пароль успешно обновлен.')

    @staticmethod
    def change_address(user, data):
        raw = text(data.get('deleted_addresses', ''), 'Адреса', 2000, False)
        if any(not item.isdigit() for item in raw.split(',') if item):
            raise ValueError('Некорректный список адресов')
        ids = [int(item) for item in raw.split(',') if item]
        if ids:
            Address.query.filter(Address.id.in_(ids), Address.person_id == user.id).delete(synchronize_session=False)
        value = text(data.get('addresses', ''), 'Адрес', 150, False)
        owned = Address.query.filter_by(person_id=user.id).all()
        if value and value not in {UserService.format_address(address) for address in owned}:
            raise ValueError('Выберите собственный адрес доставки')
        user.address = value

    @staticmethod
    def format_address(address):
        return f"г.{address.city} ул.{address.street} д.{address.home} кв.{address.flat or ''}"

    @staticmethod
    def add_address(user, data):
        address = Address(person_id=user.id,
            name=text(data.get('name', ''), 'Название', 40, False),
            city=text(data.get('city'), 'Город', 20),
            street=text(data.get('street'), 'Улица', 20),
            home=text(data.get('home'), 'Дом', 20),
            flat=text(data.get('flat', ''), 'Квартира', 20, False))
        db.session.add(address)
        db.session.flush()
        if Address.query.filter_by(person_id=user.id).count() == 1:
            user.address = UserService.format_address(address)
        db.session.commit()
        return {'success': True, 'message': 'Адрес успешно добавлен', 'address': UserService.format_address(address)}

    @staticmethod
    def add_user():
        try:
            name = text(request.form.get('name'), 'Имя', 25)
            email = valid_email(request.form.get('email'))
            password = request.form.get('password', '')
            if not 6 <= len(password) <= 128:
                raise ValueError('Пароль должен содержать от 6 до 128 символов')
            if email == current_app.config.get('ADMIN_EMAIL', '').strip().lower() or User.query.filter(func.lower(User.email) == email).first():
                raise ValueError('Аккаунт с данным Email уже зарегистрирован')
            user = User(name=name, email=email, password=generate_password_hash(password))
            db.session.add(user)
            db.session.commit()
            establish_session(user)
            return {'success': True, 'message': 'Вы успешно зарегистрировались!'}
        except ValueError as error:
            db.session.rollback()
            return {'success': False, 'message': str(error)}
        except IntegrityError:
            db.session.rollback()
            return {'success': False, 'message': 'Аккаунт с данным Email уже зарегистрирован'}

    @staticmethod
    def log_user(admin_email, admin_password):
        failure = {'success': False, 'admin': False, 'message': 'Неправильно введен пароль или Email'}
        try:
            email = valid_email(request.form.get('email'))
        except ValueError:
            return failure
        password = request.form.get('password', '')
        if not 6 <= len(password) <= 128:
            return failure
        user = User.query.filter(func.lower(User.email) == email).first()
        if not user:
            return failure
        admin = bool(admin_email and admin_password and email == admin_email.strip().lower() and password == admin_password)
        if not admin and (not user.password or not check_password_hash(user.password, password)):
            return failure
        establish_session(user, admin)
        return {'success': True, 'admin': admin, 'message': 'Вы вошли в систему!'}

    @staticmethod
    def log_user_from_google():
        from web.app.oauth import finish_google_flow
        from authlib.integrations.base_client.errors import OAuthError
        from requests.exceptions import RequestException
        try:
            claims, link_id = finish_google_flow()
            subject = claims['sub']
            google_email = valid_email(claims.get('email'))
            linked = User.query.filter_by(google_sub=subject).first()
            if link_id is not None:
                user = db.session.get(User, link_id)
                if linked is not None and linked.id != user.id:
                    raise ValueError('Этот Google-аккаунт уже привязан к другому пользователю')
                if user.google_sub and user.google_sub != subject:
                    raise ValueError('К профилю уже привязан другой Google-аккаунт')
                user.google_sub = subject
                db.session.commit()
                return {'success': True, 'message': 'Google-аккаунт привязан к профилю'}
            if linked is None:
                reserved = current_app.config.get('ADMIN_EMAIL', '').strip().lower()
                if google_email == reserved or User.query.filter(func.lower(User.email) == google_email).first():
                    raise ValueError('Этот Email уже используется. Войдите способом, выбранным при регистрации.')
                name = str(claims.get('name') or claims.get('given_name') or 'Google user').strip()[:25]
                linked = User(name=name, email=google_email, password='')
                linked.is_google = True
                linked.google_sub = subject
                db.session.add(linked)
                db.session.commit()
                log_action('registration', actor_id=linked.id, method='google')
            establish_session(linked)
            return {'success': True, 'message': 'Вы вошли через Google'}
        except ValueError as error:
            db.session.rollback()
            return {'success': False, 'message': str(error)}
        except OAuthError:
            db.session.rollback()
            current_app.logger.warning('Google отклонил авторизацию или OAuth state')
        except IntegrityError:
            db.session.rollback()
            current_app.logger.warning('Конфликт регистрации или привязки Google')
        except RequestException:
            db.session.rollback()
            current_app.logger.warning('Google OAuth временно недоступен')
        except Exception:
            db.session.rollback()
            current_app.logger.exception('Ошибка проверки Google ID token')
        return {'success': False, 'message': 'Не удалось войти через Google. Повторите попытку.'}

    @staticmethod
    def add_admin():
        email = valid_email(current_app.config.get('ADMIN_EMAIL'))
        password = current_app.config.get('ADMIN_PASSWORD', '')
        if not 6 <= len(password) <= 128:
            raise ValueError('ADMIN_PASSWORD должен содержать от 6 до 128 символов')
        if not User.query.filter(func.lower(User.email) == email).first():
            db.session.add(User(name='admin', email=email, password=generate_password_hash(password)))
            db.session.commit()
