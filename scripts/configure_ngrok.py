#!/usr/bin/env python3
"""Prepare the local env for an HTTPS tunnel without changing Telegram remotely."""
import argparse
from pathlib import Path
import re
import secrets
from urllib.parse import urlsplit
from dotenv import dotenv_values, set_key

ROOT=Path(__file__).resolve().parents[1]


def configure(url, env_file):
    base=url.strip().rstrip('/')
    parsed=urlsplit(base)
    if parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment:
        raise ValueError('Укажите HTTPS-адрес ngrok без пути, например https://example.ngrok-free.app')
    if not env_file.is_file():
        raise ValueError('Сначала выполните python scripts/local_db.py setup')
    values=dotenv_values(env_file)
    selected=urlsplit(values.get('DATABASE_URL') or '')
    if selected.hostname not in {'127.0.0.1','localhost'} or selected.path!='/kodee_dev':
        raise ValueError('Этот помощник изменяет только настройки локальной kodee_dev')
    secret=values.get('BOT_WEBHOOK_SECRET') or secrets.token_urlsafe(32)
    if not re.fullmatch(r'[A-Za-z0-9_-]{32,256}',secret):
        raise ValueError('BOT_WEBHOOK_SECRET должен содержать 32–256 букв, цифр, _ и -')
    updates={
        'APP_BASE_URL':base,'WEBHOOK_URL':base+'/bot/webhook',
        'TRUSTED_HOSTS':parsed.hostname+',127.0.0.1,localhost',
        'TRUSTED_PROXY_CIDRS':'127.0.0.1/32,::1/128',
        'PROXY_X_FOR':'1','PROXY_X_PROTO':'1','PROXY_X_HOST':'0','PROXY_X_PORT':'0',
        'PUBLIC_HTTPS':'false','SESSION_COOKIE_SECURE':'true','BOT_WEBHOOK_SECRET':secret,
    }
    for key,value in updates.items():
        set_key(str(env_file),key,value,quote_mode='always')
    env_file.chmod(0o600)
    return base


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('url')
    args=parser.parse_args()
    try:
        base=configure(args.url,ROOT/'.env.local')
    except ValueError as error:
        raise SystemExit(str(error))
    print(f'Настроено: {base}; секрет сохранён в .env.local без вывода в терминал')
    print('BOT_TOKEN и BOT_ALLOWED_USER_IDS сохранены. Перезапустите локальное приложение.')
    print('После запуска: KODEE_ENV_FILE=.env.local .venv/bin/python -m flask --app main set-bot-webhook')


if __name__=='__main__':main()
