"""Explicit, idempotent schema maintenance; never run against data on import."""
from collections import defaultdict
import click
from flask import current_app
from sqlalchemy import inspect, text
from db.models import db, User, Product, Product_image

STOCK_COLUMNS = ('gold', 'silver', 'form_gold', 'form_silver', 'price', 'price_chet', 'weight', 'G')


def upgrade_schema():
    # Abort before modifying existing users if duplicates/invalid amounts need review.
    tables = inspect(db.engine).get_table_names()
    if 'users' in tables:
        # Reflection also handles databases from before google_sub was introduced.
        columns = {column['name'] for column in inspect(db.engine).get_columns('users')}
        projection = 'id, email, telegram_id' + (', google_sub' if 'google_sub' in columns else '')
        emails, telegram, subjects = defaultdict(list), defaultdict(list), defaultdict(list)
        for user in db.session.execute(text('SELECT ' + projection + ' FROM users')).mappings():
            if user['email'] and user['email'].strip():
                emails[user['email'].strip().lower()].append(user['id'])
            if user['telegram_id'] is not None:
                telegram[user['telegram_id']].append(user['id'])
            if user.get('google_sub'):
                subjects[user['google_sub']].append(user['id'])
        duplicates = [ids for group in (emails, telegram, subjects) for ids in group.values() if len(ids) > 1]
        if duplicates:
            raise click.ClickException(f'Дубликаты пользователей: {duplicates}. Разрешите конфликты перед миграцией.')
    if 'product' in tables:
        invalid = [p.id for p in Product.query.all() if any(getattr(p, field) is not None and getattr(p, field) < 0 for field in STOCK_COLUMNS)]
        if invalid:
            raise click.ClickException(f'Отрицательные значения у товаров {invalid}. Исправьте перед миграцией.')
    if 'product_image' in tables:
        groups = defaultdict(list)
        invalid = []
        for image in Product_image.query.all():
            groups[(image.product_id, image.num)].append(image.id)
            if image.num not in range(1, 5):
                invalid.append(image.id)
        duplicates = [ids for ids in groups.values() if len(ids) > 1]
        if duplicates or invalid:
            raise click.ClickException(f'Проверьте изображения: дубликаты {duplicates}, неверные номера {invalid}')
    db.session.rollback()
    if 'users' in tables and 'google_sub' not in {column['name'] for column in inspect(db.engine).get_columns('users')}:
        with db.engine.begin() as connection:
            connection.execute(text('ALTER TABLE users ADD COLUMN google_sub VARCHAR(255)'))
    db.create_all()
    from customer_bot.storage import metadata as customer_metadata
    customer_metadata.create_all(db.engine)
    # Prototype deployments may already have the original customer outbox.
    if 'target' not in {column['name'] for column in inspect(db.engine).get_columns('cb_outbox')}:
        with db.engine.begin() as connection:
            connection.execute(text("ALTER TABLE cb_outbox ADD COLUMN target VARCHAR(16) NOT NULL DEFAULT 'customer'"))
    with db.engine.begin() as connection:
        connection.execute(text("UPDATE users SET email = NULLIF(lower(trim(email)), '')"))
        connection.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_users_email_normalized ON users (lower(NULLIF(trim(email), '')))"))
        connection.execute(text('CREATE UNIQUE INDEX IF NOT EXISTS uq_users_telegram_id ON users (telegram_id)'))
        connection.execute(text('CREATE UNIQUE INDEX IF NOT EXISTS uq_users_google_sub ON users (google_sub)'))
        connection.execute(text('CREATE UNIQUE INDEX IF NOT EXISTS uq_product_image_number ON product_image (product_id, num)'))
        if connection.dialect.name == 'postgresql':
            connection.execute(text('ALTER TABLE users ALTER COLUMN address TYPE VARCHAR(150)'))
            constraints = {constraint['name'] for constraint in inspect(connection).get_check_constraints('product')}
            image_constraints = {item['name'] for item in inspect(connection).get_check_constraints('product_image')}
            if 'ck_product_image_number' not in image_constraints:
                connection.execute(text('ALTER TABLE product_image ADD CONSTRAINT ck_product_image_number CHECK (num BETWEEN 1 AND 4 AND num IS NOT NULL)'))
            for field in STOCK_COLUMNS:
                name = f'ck_product_{field}_nonnegative'
                if name not in constraints:
                    connection.execute(text(f'ALTER TABLE product ADD CONSTRAINT "{name}" CHECK ("{field}" >= 0)'))
        elif connection.dialect.name == 'sqlite':
            # Existing SQLite tables cannot acquire CHECK via ALTER TABLE.
            for operation in ('INSERT', 'UPDATE'):
                connection.execute(text(f"CREATE TRIGGER IF NOT EXISTS image_number_{operation.lower()} BEFORE {operation} ON product_image WHEN NEW.num IS NULL OR NEW.num NOT BETWEEN 1 AND 4 BEGIN SELECT RAISE(ABORT, 'invalid image number'); END"))
                condition = ' OR '.join(f'NEW.{field} < 0' for field in STOCK_COLUMNS)
                connection.execute(text(f"CREATE TRIGGER IF NOT EXISTS product_nonnegative_{operation.lower()} BEFORE {operation} ON product WHEN {condition} BEGIN SELECT RAISE(ABORT, 'negative product value'); END"))
        else:
            raise click.ClickException('Поддерживаются PostgreSQL и SQLite')


def register_commands(app):
    @app.cli.command('upgrade-db')
    def upgrade_db():
        """Create missing tables and apply audited schema constraints."""
        upgrade_schema()
        click.echo('Схема базы данных обновлена')

    @app.cli.command('create-admin')
    def create_admin():
        from web.app.services.user import UserService
        UserService.add_admin()
        click.echo('Администратор готов')

    @app.cli.command('set-bot-webhook')
    def set_webhook():
        from bot.bot.bot import configure_webhook
        try:
            configure_webhook(current_app)
        except ValueError as error:
            raise click.ClickException(str(error)) from error
        except Exception as error:
            current_app.logger.warning('Не удалось установить webhook (%s)',type(error).__name__)
            raise click.ClickException('Telegram API не подтвердил настройку. Проверьте BOT_TOKEN и доступность WEBHOOK_URL.') from None
        click.echo('Webhook установлен')

    @app.cli.command('seed-products')
    def seed_products():
        """Insert missing catalog entries from db/add_products.py, preserving existing entries."""
        from db.add_products import allProducts
        count = allProducts(db, current_app)
        click.echo(f'Добавлено товаров: {count}')

    @app.cli.command('bot-status')
    def bot_status():
        """Read Telegram webhook settings without displaying the bot token."""
        bot=current_app.extensions.get('telegram_bot')
        if not bot:
            raise click.ClickException('BOT_TOKEN не задан')
        try:
            info=bot.get_webhook_info(timeout=10)
        except Exception as error:
            current_app.logger.warning('Не удалось прочитать настройки webhook (%s)',type(error).__name__)
            raise click.ClickException('Telegram API недоступен; детали в серверных журналах') from None
        click.echo(f'URL: {info.url or "не установлен"}')
        click.echo(f'Ожидает обновлений: {info.pending_update_count}')
        error=getattr(info,'last_error_message',None) or 'нет'
        for secret in (current_app.config.get('BOT_TOKEN'),current_app.config.get('BOT_WEBHOOK_SECRET')):
            if secret:
                error=error.replace(secret,'[hidden]')
        click.echo(f'Последняя ошибка: {error}')

    @app.cli.command('bind-google')
    @click.option('--user-id', required=True, type=click.IntRange(min=1))
    @click.option('--subject', required=True, help='Verified Google sub, never an email or access token.')
    def bind_google(user_id, subject):
        """Explicit operator migration for a legacy Google account without a sub."""
        if not 1 <= len(subject) <= 255 or any(char.isspace() for char in subject):
            raise click.ClickException('Некорректный Google sub')
        user = db.session.get(User, user_id)
        linked = User.query.filter_by(google_sub=subject).first()
        if not user or (linked and linked.id != user.id) or (user.google_sub and user.google_sub != subject):
            raise click.ClickException('Пользователь не найден или привязка конфликтует с существующей')
        user.google_sub = subject
        db.session.commit()
        click.echo(f'Google sub привязан к пользователю ID {user_id}')
