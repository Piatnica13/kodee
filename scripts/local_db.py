#!/usr/bin/env python3
"""Own local PostgreSQL cluster. Never reads DATABASE_URL or the production .env."""
import argparse
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import tempfile
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / '.local' / 'postgres'
DATA = LOCAL / 'data'
CONFIG = LOCAL / 'connection.json'
ENV_FILE = ROOT / '.env.local'
PORT = 55439
ROLE = 'kodee_local'
DATABASES = ('kodee_dev', 'kodee_test')


def binary(name):
    path = shutil.which(name)
    if path:
        return path
    candidates = sorted(Path('/usr/lib/postgresql').glob(f'*/bin/{name}'), key=lambda p: int(p.parents[1].name), reverse=True)
    if not candidates:
        raise SystemExit('Установите PostgreSQL 18 и запускайте скрипт из .venv')
    return str(candidates[0])


def settings():
    LOCAL.mkdir(parents=True, exist_ok=True, mode=0o700)
    if not CONFIG.exists():
        config = {'password': secrets.token_urlsafe(32), 'port': PORT, 'role': ROLE}
        with CONFIG.open('x') as output:
            os.chmod(CONFIG, 0o600)
            json.dump(config, output)
    return json.loads(CONFIG.read_text())


def dsn(config, database):
    return f"postgresql://{ROLE}:{quote(config['password'], safe='')}@127.0.0.1:{PORT}/{database}"


def write_env(config):
    if ENV_FILE.exists():
        return
    values = {
        'SECRET_KEY': secrets.token_urlsafe(48), 'DATABASE_URL': dsn(config, 'kodee_dev'),
        'KODEE_TEST_DATABASE_URL': dsn(config, 'kodee_test'),
        'LOG_DIR': '.local/logs',
        'ADMIN_EMAIL': 'admin@example.com', 'ADMIN_PASSWORD': secrets.token_urlsafe(24),
        'APP_BASE_URL': 'http://127.0.0.1:5000', 'SESSION_COOKIE_SECURE': 'false',
        'TRUSTED_HOSTS': '127.0.0.1,localhost', 'TRUSTED_PROXY_CIDRS': '',
        'PROXY_X_FOR': '0', 'PROXY_X_PROTO': '0', 'PROXY_X_HOST': '0', 'PROXY_X_PORT': '0',
        'GOOGLE_CLIENT_ID': '', 'GOOGLE_CLIENT_SECRET': '',
        'BOT_TOKEN': '', 'BOT_ALLOWED_USER_IDS': '',
        'BOT_WEBHOOK_SECRET': secrets.token_urlsafe(32), 'WEBHOOK_URL': '', 'WEB_WORKERS':'2',
    }
    with ENV_FILE.open('x') as output:
        os.chmod(ENV_FILE, 0o600)
        output.write('# Local development only. Generated secrets: do not commit.\n')
        output.write(''.join(f'{key}={value}\n' for key,value in values.items()))


def start():
    config = settings()
    write_env(config)
    if not (DATA / 'PG_VERSION').exists():
        with tempfile.NamedTemporaryFile(mode='w',dir=LOCAL) as password:
            password.write(config['password']+'\n')
            password.flush()
            subprocess.run([binary('initdb'),'-D',str(DATA),'-U',ROLE,'-A','scram-sha-256',
                            '--pwfile',password.name,'--no-locale','-E','UTF8'],check=True)
    status = subprocess.run([binary('pg_ctl'),'-D',str(DATA),'status'],capture_output=True)
    if status.returncode:
        subprocess.run([binary('pg_ctl'),'-D',str(DATA),'-l',str(LOCAL/'server.log'),
                        '-o',f'-h 127.0.0.1 -p {PORT} -k {LOCAL}', 'start'],check=True)
    import psycopg2
    from psycopg2 import sql
    connection = psycopg2.connect(dsn(config,'postgres'))
    try:
        connection.autocommit = True
        with connection.cursor() as cursor:
            for database in DATABASES:
                cursor.execute('SELECT 1 FROM pg_database WHERE datname=%s',(database,))
                if cursor.fetchone() is None:
                    cursor.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(database)))
    finally:
        connection.close()
    print(f'Local PostgreSQL: 127.0.0.1:{PORT}; databases: kodee_dev, kodee_test')
    print('Local environment: .env.local (existing file is preserved)')
    return config


def run_local(*args):
    env = os.environ.copy()
    env['KODEE_ENV_FILE'] = str(ENV_FILE)
    subprocess.run([sys.executable,*args],cwd=ROOT,env=env,check=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['start','stop','status','setup','seed','test'])
    args=parser.parse_args()
    if args.command in {'stop','status'}:
        result=subprocess.run([binary('pg_ctl'),'-D',str(DATA),args.command])
        raise SystemExit(result.returncode)
    config=start()
    if args.command in {'setup','seed'}:
        from dotenv import dotenv_values
        selected = dotenv_values(ENV_FILE).get('DATABASE_URL')
        if selected != dsn(config,'kodee_dev'):
            raise SystemExit('.env.local DATABASE_URL отличается от локальной базы; схема не изменена')
        if args.command=='setup':
            run_local('-m','flask','--app','main','upgrade-db')
            run_local('-m','flask','--app','main','create-admin')
        else:
            run_local('-m','flask','--app','main','seed-products')
    elif args.command=='test':
        env=os.environ.copy()
        env['KODEE_TEST_DATABASE_URL']=dsn(config,'kodee_test')
        subprocess.run([sys.executable,'-m','unittest','discover','-s','tests','-v'],cwd=ROOT,env=env,check=True)


if __name__=='__main__':
    main()
