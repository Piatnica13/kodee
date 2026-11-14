"""Only configured employees may use the private inventory bot."""
from flask import current_app


def allowed(message, actor=None):
    actor = actor or message.from_user
    ids = current_app.config.get('BOT_ALLOWED_USER_IDS', set())
    return bool(actor and not actor.is_bot and message.chat.type == 'private'
                and actor.id == message.chat.id and actor.id in ids)
