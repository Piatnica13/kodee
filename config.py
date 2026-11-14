import os
from pathlib import Path
from dotenv import load_dotenv


def load_environment():
    explicit = os.getenv('KODEE_ENV_FILE')
    if explicit:
        if not Path(explicit).is_file():
            raise RuntimeError('Файл KODEE_ENV_FILE не найден')
        load_dotenv(explicit, override=True)
    else:
        load_dotenv('.password.env')
        load_dotenv('.env')


class Config:
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {'pool_pre_ping': True, 'hide_parameters': True}
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    MAX_CONTENT_LENGTH = 34 * 1024 * 1024
    MAX_FORM_MEMORY_SIZE = 512 * 1024
    OAUTH_FLOW_TTL = 600
    DEBUG = True
