from flask import session, current_app
from db.models import User, db
import os


def current_user():
    user_id = session.get('user_id')
    if not isinstance(user_id, int) or isinstance(user_id, bool):
        session.pop('user_id', None)
        session.pop('admin', None)
        return None
    user = db.session.get(User, user_id)
    if user is None:
        session.pop('user_id', None)
        session.pop('admin', None)
    return user


def is_admin():
    user = current_user()
    admin_email = current_app.config.get('ADMIN_EMAIL', '').strip().lower()
    return bool(user and admin_email and session.get('admin') is True and user.email and user.email.lower() == admin_email)


def establish_session(user, admin=False):
    session.clear()
    session['user_id'] = user.id
    session['admin'] = bool(admin)
