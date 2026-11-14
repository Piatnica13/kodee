# Kodee

Интернет-каталог KoDee Desire и служебный Telegram-бот для работы с товарами, остатками, продажами и сертификатами.

Посетитель может открыть каталог, найти товар и посмотреть его страницу без регистрации. После входа доступны профиль, адреса доставки, избранное и корзина. Заказ из корзины оформляется через WhatsApp: сайт подготавливает сообщение, а отправляет его покупатель. Онлайн-оплаты и отдельной модели заказа в проекте нет.

## Что используется

- Python 3.14, Flask и Jinja2 — сервер и HTML-страницы.
- PostgreSQL, SQLAlchemy и Flask-SQLAlchemy — хранение данных.
- Flask-WTF — формы и CSRF.
- Authlib — вход через Google по OpenID Connect.
- Flask-Admin — административная панель.
- pyTelegramBotAPI — служебный бот.
- Pillow — проверка фотографий и преобразование в WEBP.
- ReportLab — PDF-сертификаты.
- Обычные JavaScript и CSS — интерфейс. Node.js нужен только для проверки синтаксиса JS; сборки frontend нет.
- Gunicorn — запуск приложения, Docker — упаковка.

Версии Python-пакетов зафиксированы в `requirements.txt`.

## Быстрый локальный запуск

Все команды ниже выполняются из корня проекта. Для автоматической настройки PostgreSQL нужны Linux, Python 3.14 и установленные серверные утилиты PostgreSQL 18: `initdb` и `pg_ctl`. Запускайте их от обычного пользователя, не от root.

```bash
python3.14 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python scripts/local_db.py setup
python scripts/local_db.py seed
KODEE_ENV_FILE=.env.local python main.py
```

Откройте **http://127.0.0.1:5000**. Для локального HTTP Secure-cookie отключена только в `.env.local`.

`setup` создаёт собственный кластер в `.local/postgres/data`, запускает его на `127.0.0.1:55439`, создаёт две базы и настраивает приложение:

| База | Для чего используется |
|---|---|
| `kodee_dev` | Локальный сайт, каталог и администратор |
| `kodee_test` | Автоматические тесты; её таблицы создаются и удаляются при проверках |

Пользователь PostgreSQL — `kodee_local`. Пароли БД, пароль администратора и ключ сессий генерируются автоматически. Они находятся в `.env.local`; пароль подключения к кластеру также хранится в `.local/postgres/connection.json`. Скрипт не выводит пароли и не читает рабочий `DATABASE_URL` из `.env`.

`seed` добавляет исходный каталог из `db/add_products.py`. Повторный запуск не меняет уже существующие товары. Цены берутся из исходного кода, а не из рабочей базы. Начальные остатки равны нулю. В комплекте 51 товар и фотографии в `web/static/image/productImgs`.

Управление локальной БД:

```bash
python scripts/local_db.py status
python scripts/local_db.py stop
python scripts/local_db.py start
```

Остановка не удаляет данные. Повторный `setup` сохраняет существующие `.env.local`, пользователей и товары. Если `DATABASE_URL` в `.env.local` больше не соответствует созданной локальной базе, скрипт откажется менять схему.

Для входа в админку откройте `/login`. Email и пароль администратора указаны в `.env.local` как `ADMIN_EMAIL` и `ADMIN_PASSWORD`. После входа панель находится по адресу `/admin/`.

### Если PostgreSQL уже установлен и настроен отдельно

Можно использовать собственную **локальную** базу. Создайте роль и базу средствами PostgreSQL, скопируйте `.env.example` в отдельный игнорируемый env-файл и измените настройки:

```dotenv
DATABASE_URL=postgresql://your_user:your_password@127.0.0.1:5432/kodee_dev
APP_BASE_URL=http://127.0.0.1:5000
SESSION_COOKIE_SECURE=false
TRUSTED_HOSTS=127.0.0.1,localhost
TRUSTED_PROXY_CIDRS=
PROXY_X_FOR=0
PROXY_X_PROTO=0
PROXY_X_HOST=0
PROXY_X_PORT=0
```

Затем выполните `upgrade-db` и `create-admin`, указав этот env-файл через `KODEE_ENV_FILE`. Спецсимволы в пароле внутри URL нужно кодировать как URL-компонент.

## Конфигурация

Секреты не нужно добавлять в Python-файлы. Используйте переменные окружения или env-файл.

Порядок загрузки:

1. Если задан `KODEE_ENV_FILE`, читается только выбранный файл. Его значения имеют приоритет над одноимёнными переменными процесса. Это позволяет явно выбрать локальную БД, даже если в оболочке остался другой `DATABASE_URL`.
2. Если `KODEE_ENV_FILE` не задан, уже установленные переменные процесса имеют приоритет. Недостающие значения берутся сначала из `.password.env`, затем из `.env`.
3. `.env.local` автоматически не подключается — укажите его явно.

Тот же порядок применяется к конфигурации Gunicorn. Выбранный файл должен существовать; при ошибке пути приложение остановится, а не перейдёт к другому env-файлу.

| Переменная | Назначение |
|---|---|
| `SECRET_KEY` | Секрет подписи сессий и CSRF. Обязателен, одинаков для всех workers |
| `DATABASE_URL` | Подключение SQLAlchemy к выбранной БД. Обязательно |
| `ADMIN_EMAIL` | Email административного аккаунта; зарезервирован от обычной регистрации |
| `ADMIN_PASSWORD` | Пароль административного входа и начальный пароль при `create-admin` |
| `APP_BASE_URL` | Основной адрес сайта без пути и завершающего `/`, например `https://kodee.kz` |
| `PUBLIC_HTTPS` | `true` только за ingress, который гарантирует внешний HTTPS (например Render). Фиксирует внешнюю схему без доверия к заголовкам клиента; требует `PROXY_X_PROTO=0` |
| `PRODUCT_IMAGES_DIR` | Постоянный каталог новых фотографий. Если пусто — `web/static/image/productImgs`; исходные фото остаются fallback |
| `SESSION_COOKIE_SECURE` | `true` для HTTPS, `false` только для локального HTTP. По умолчанию определяется схемой `APP_BASE_URL` |
| `TRUSTED_HOSTS` | Допустимые Host через запятую, без схемы и пути. Если пусто — hostname из `APP_BASE_URL` |
| `TRUSTED_PROXY_CIDRS` | IP/CIDR непосредственных доверенных proxy через запятую. Пустое значение отключает доверие forwarded-заголовкам |
| `PROXY_X_FOR` | Сколько последних значений `X-Forwarded-For` учитывать; по умолчанию `0` |
| `PROXY_X_PROTO` | Сколько значений `X-Forwarded-Proto` учитывать; по умолчанию `0` |
| `PROXY_X_HOST` | Сколько значений `X-Forwarded-Host` учитывать; по умолчанию `0` |
| `PROXY_X_PORT` | Сколько значений `X-Forwarded-Port` учитывать; по умолчанию `0` |
| `GOOGLE_CLIENT_ID` | Client ID веб-приложения Google |
| `GOOGLE_CLIENT_SECRET` | Client Secret того же приложения Google |
| `BOT_TOKEN` | Токен от BotFather. Если пусто, бот отключён, сайт продолжает работать |
| `BOT_ALLOWED_USER_IDS` | Разрешённые Telegram user ID через запятую; пусто — никто не допущен |
| `BOT_WEBHOOK_SECRET` | Отдельный секрет webhook из 32–256 букв, цифр, `_` и `-` |
| `WEBHOOK_URL` | Публичный HTTPS URL `/bot/webhook` |
| `PORT` | Порт приложения; по умолчанию `5000` |
| `WEB_WORKERS` | Количество процессов Gunicorn; по умолчанию `2` |
| `GUNICORN_BIND` | Полный bind Gunicorn; по умолчанию `0.0.0.0:$PORT` |
| `LOG_DIR` | Каталог журналов; по умолчанию `logs` |
| `KODEE_TEST_DATABASE_URL` | Только для тестов: локальная PostgreSQL `kodee_test` |

Файлы `.env*`, `.password.env`, `.local/`, журналы, сертификаты, виртуальное окружение и `audit/` исключены из Git. `.env.example` содержит только пример. Локальные данные и секреты также исключены из Docker-контекста.

Сгенерировать отдельный секрет можно так:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Для `SECRET_KEY` и `BOT_WEBHOOK_SECRET` используйте разные значения.

## Локальная проверка через ngrok

Ошибка `Host '...ngrok-free.app' is not trusted` означает, что домен туннеля отсутствует в `TRUSTED_HOSTS`. `BOT_ALLOWED_USER_IDS` отвечает за доступ сотрудников к боту и не связан с проверкой HTTP Host.

Для этой структуры проекта команды Flask запускаются через `python -m flask`: так Python видит корень проекта при импорте модулей.

1. Запустите локальную PostgreSQL:

```bash
.venv/bin/python scripts/local_db.py start
```

2. Запустите ngrok, если он ещё не работает:

```bash
ngrok http http://127.0.0.1:5000
```

Если туннель уже запущен, используйте его текущий HTTPS URL, второй туннель не нужен. Не добавляйте `--host-header=rewrite`: приложение должно видеть настоящий публичный Host.

3. Подставьте полученный URL в команду:

```bash
.venv/bin/python scripts/configure_ngrok.py https://YOUR_DOMAIN.ngrok-free.app
```

Помощник обновит **только `.env.local` для локальной `kodee_dev`**: основной адрес, допустимые Host, HTTPS-cookie, адрес webhook и доверие к локальному агенту ngrok. `BOT_TOKEN` и список разрешённых ID сохраняются. Если `BOT_WEBHOOK_SECRET` пуст, он будет сгенерирован и сохранён без вывода в терминал.

Получатся такие настройки (домен замените текущим):

```dotenv
APP_BASE_URL=https://YOUR_DOMAIN.ngrok-free.app
WEBHOOK_URL=https://YOUR_DOMAIN.ngrok-free.app/bot/webhook
TRUSTED_HOSTS=YOUR_DOMAIN.ngrok-free.app,127.0.0.1,localhost
TRUSTED_PROXY_CIDRS=127.0.0.1/32,::1/128
PROXY_X_FOR=1
PROXY_X_PROTO=1
PROXY_X_HOST=0
PROXY_X_PORT=0
PUBLIC_HTTPS=false
SESSION_COOKIE_SECURE=true
```

4. **Остановите старый процесс сайта через Ctrl+C** и запустите его с обновлённым env:

```bash
KODEE_ENV_FILE=.env.local .venv/bin/python main.py
```

Изменение env-файла не меняет настройки уже работающего процесса. Во время этой проверки открывайте сайт по HTTPS-адресу ngrok: страницы входа используют `APP_BASE_URL`.

5. Проверьте `https://YOUR_DOMAIN.ngrok-free.app/healthz`: должен вернуться `{"status":"ok"}`. Это проверка процесса, а не состояния схемы БД.

6. В другом терминале установите webhook и прочитайте его состояние:

```bash
KODEE_ENV_FILE=.env.local .venv/bin/python -m flask --app main set-bot-webhook
KODEE_ENV_FILE=.env.local .venv/bin/python -m flask --app main bot-status
```

7. Отправьте `/start` своему боту. Проверьте меню, просмотр товара, изменение остатка и запись продажи в локальной базе. Для пользователя должен быть задан числовой ID в `BOT_ALLOWED_USER_IDS`.

`bot-status` не меняет настройки Telegram: показывает URL, очередь обновлений и последнюю ошибку. При повторном ngrok-запуске с новым доменом повторите шаги 3–6. Не включайте ngrok OAuth/Basic Auth перед `/bot/webhook`: Telegram должен иметь возможность сделать POST с секретным заголовком.

Если одновременно проверяете Google-вход через туннель, добавьте точный `https://YOUR_DOMAIN.ngrok-free.app/callback` в Google Cloud. Менять настройки рабочей БД для этого не нужно.

## Google OAuth

### Настройка Google

1. Откройте Google Cloud Console и выберите проект.
2. Настройте Google Auth Platform: сведения о приложении, аудиторию и тестовых пользователей, если приложение работает в режиме Testing.
3. Создайте OAuth client типа **Web application**.
4. Добавьте точные Authorized redirect URIs:

```text
http://127.0.0.1:5000/callback
https://kodee.kz/callback
```

Если основной домен или порт другой, измените URI соответственно. Для варианта `http://localhost:5000` нужен отдельный URI и соответствующий `APP_BASE_URL`. Не смешивайте `localhost` и `127.0.0.1` в одном сеансе: у них разные cookies.

5. Запишите `GOOGLE_CLIENT_ID` и `GOOGLE_CLIENT_SECRET` в выбранный env-файл.
6. Перезапустите приложение и откройте `/login` на адресе из `APP_BASE_URL`.

Без обоих ключей кнопка Google скрыта, а прямой запрос `/login/google` возвращает 503. Обычный вход продолжает работать.

### Как устроен вход

Приложение создаёт OAuth `state`, nonce и PKCE. Callback всегда строится из `APP_BASE_URL`, а не из присланного пользователем Host. Authlib проверяет `state`, подпись ID token, nonce, issuer, audience и срок действия. Для Google также проверяется `email_verified`. Письмо пользователю приложение не отправляет.

Google-аккаунт определяется по `google_sub` — постоянному Google `sub`. Email профиля можно менять без подтверждения; при следующем входе через Google поиск всё равно идёт по `sub`, а email не перезаписывается данными провайдера.

Если email из Google уже занят локальным аккаунтом, автоматического объединения нет. Войдите в существующий аккаунт, откройте профиль и нажмите **«Привязать Google-аккаунт»**. Привязка защищена сессией и CSRF; один Google `sub` не может принадлежать двум профилям. Google-вход не выдаёт права администратора автоматически.

Для старых Google-аккаунтов, созданных до появления `google_sub`, возможна явная операторская миграция:

```bash
KODEE_ENV_FILE=.env.local python -m flask --app main bind-google --user-id USER_ID --subject VERIFIED_GOOGLE_SUB
```

Это команда администратора сервера. Используйте `sub`, принадлежность которого нужному пользователю проверена; не подставляйте email, access token или данные из непроверенного JWT. Обычным пользователям достаточно привязки через профиль.

## Telegram-бот

Бот работает через webhook, не через polling. Он предназначен для сотрудников и принимает служебные действия только в личных чатах.

### Где задавать параметры

Для локального запуска редактируйте `.env.local`; для сервера — используемый env-файл или настройки переменных окружения платформы:

```dotenv
BOT_TOKEN=token_from_BotFather
BOT_ALLOWED_USER_IDS=123456789,987654321
BOT_WEBHOOK_SECRET=paste_a_separately_generated_secret_here
WEBHOOK_URL=https://kodee.kz/bot/webhook
```

- `BOT_ALLOWED_USER_IDS` — **числовые ID людей**, а не `@username`, имя бота или ID группы. Указанные числа в примере нужно заменить своими. Добавляйте сотрудников через запятую без кавычек вокруг каждого ID.
- `BOT_WEBHOOK_SECRET` генерируется отдельно командой из раздела конфигурации. Это не `BOT_TOKEN` и не пароль администратора.
- `WEBHOOK_URL` — адрес, доступный серверам Telegram по HTTPS. `http://127.0.0.1:5000/bot/webhook` для этого не подходит. Для локальной проверки с настоящим Telegram нужен публичный HTTPS-туннель, направленный на локальный сервер, либо отдельный тестовый сервер/бот.

Токен бота создаётся в [BotFather](https://t.me/BotFather).

### Как узнать свой user ID

Когда бот и webhook уже настроены, отправьте своему боту `/start`. Даже если список разрешённых ID пока пуст, сервер запишет отклонённое обращение:

```text
Отклонено неразрешённое обращение к боту, user_id=123456789
```

Найдите запись в серверных логах, внесите этот ID в `BOT_ALLOWED_USER_IDS` и перезапустите приложение. Для каждого сотрудника повторите тот же шаг. Никому не нужно сообщать токен бота.

### Установка webhook

После настройки переменных и перезапуска приложения выполните:

```bash
KODEE_ENV_FILE=.env.local python -m flask --app main set-bot-webhook
```

Для сервера укажите его env-файл. Команда регистрирует команды бота и передаёт Telegram URL и секрет. Затем Telegram добавляет `X-Telegram-Bot-Api-Secret-Token` к каждому запросу; сервер проверяет его до обработки сообщения.

При смене URL или секрета повторите команду. При изменении только `BOT_ALLOWED_USER_IDS` достаточно перезапуска приложения. Если одновременно использовать локальную и рабочую версии, создайте отдельный тестовый бот: у одного бота один активный webhook.

`python -m flask --app main bot-status` показывает текущий webhook и последнюю ошибку без изменения настроек. Публичного `/bot/setwebhook` нет. При неверном секрете `/bot/webhook` отвечает 403, а при отключённом/неполностью настроенном боте — 503.

### Возможности и состояние

Сотрудник может просматривать каталог, изменять товары и фотографии, управлять остатками, учитывать продажи и эксклюзивные изделия, смотреть депозит и работать с упрощёнными сертификатами. Категории seller/worker не заменяют список допуска: изменение категории не добавляет новый Telegram ID в разрешённые.

Диалоги хранятся в `bot_states` и истекают через час бездействия. В PostgreSQL операции одного сотрудника сериализуются advisory lock. Для SQLite используется локальная файловая блокировка; несколько серверов с SQLite не поддерживаются.

Внутренние исключения и traceback пишутся в журналы, а не отправляются в Telegram.

## База данных и команды

| Модель / таблица | Данные |
|---|---|
| `User` / `users` | Профиль, хеш пароля, email, Telegram ID, Google sub, корзина и избранное |
| `Address` / `address` | Адреса доставки пользователя |
| `Product` / `product` | Товар, slug, цены, вес, материал и остатки |
| `Product_image` / `product_image` | До четырёх номеров фотографий товара |
| `Sale` / `sale` | Записи продаж с ценой и количеством на момент операции |
| `Exclusive` / `exclusive` | Индивидуальные изделия |
| `Certificate` / `certificate` | Упрощённые сертификаты |
| `BotState` / `bot_states` | Состояние диалогов бота |

Импорт приложения не создаёт таблицы и не подключается к Telegram API. Перед первым запуском БД нужно подготовить явно:

```bash
KODEE_ENV_FILE=.env.local python -m flask --app main upgrade-db
KODEE_ENV_FILE=.env.local python -m flask --app main create-admin
```

`upgrade-db` создаёт отсутствующие таблицы, добавляет `google_sub` старым базам, нормализует email и устанавливает уникальные индексы и ограничения числовых значений/изображений. Команда повторно применима. При дубликатах пользователей, Google sub, номеров фотографий или отрицательных значениях она остановится с указанием ID, не удаляя спорные данные автоматически.

`create-admin` создаёт отсутствующий аккаунт из `ADMIN_EMAIL`/`ADMIN_PASSWORD`; существующий профиль не удаляется и его хеш пароля автоматически не переписывается. Административный вход связан с настроенным `ADMIN_EMAIL`. При изменении email административного аккаунта обновите этот параметр на сервере.

Исходный каталог добавляется отдельно:

```bash
KODEE_ENV_FILE=.env.local python -m flask --app main seed-products
```

Команда не обновляет существующие товары и цены. Для рабочего каталога изменения делаются в админке или боте.

Изменение остатка и запись продажи выполняются одной транзакцией. Продажа не может опустить остаток ниже нуля. Удаление товара сохраняет историю продаж.

## Фотографии и сертификаты

Фотографии доступны из `web/static/image/productImgs/<slug>/img1.webp` … `img4.webp`. При загрузке принимаются JPEG, PNG и WEBP до 8 МиБ и 20 мегапикселей на изображение. Сервер декодирует файл и сохраняет WEBP. Имена файлов задаёт приложение. Для номера фотографии действует уникальность в рамках товара.

При неуспешной публикации/транзакции предыдущие файлы восстанавливаются. Slug существующего товара сохраняется при переименовании, чтобы не ломать адреса и фотографии.

Временный PDF-сертификат создаётся в `certificates/`, отправляется через бота и удаляется после попытки отправки. Правила выпуска и активации намеренно оставлены упрощёнными.

При развёртывании обеспечьте постоянное хранилище фотографий. Для Docker каталог должен быть доступен UID 10001. PostgreSQL и фотографии резервируются отдельно; один дамп БД не содержит загруженных файлов.

## Запуск через Gunicorn и proxy

Без reverse proxy не задавайте доверенные CIDR и оставляйте hop counts равными нулю. Для одного локального Nginx перед Gunicorn пример настроек такой:

```dotenv
APP_BASE_URL=https://kodee.kz
SESSION_COOKIE_SECURE=true
TRUSTED_HOSTS=kodee.kz,www.kodee.kz
TRUSTED_PROXY_CIDRS=127.0.0.1/32
PROXY_X_FOR=1
PROXY_X_PROTO=1
PROXY_X_HOST=1
PROXY_X_PORT=1
GUNICORN_BIND=127.0.0.1:5000
```

```bash
KODEE_ENV_FILE=.env.production gunicorn -c gunicorn.conf.py main:app
```

Готовый пример Nginx находится в [`deploy/nginx.conf.example`](deploy/nginx.conf.example). В нём нужно проверить домены и пути сертификата перед использованием. Для хостинга/CDN с другой схемой укажите адреса **непосредственного** proxy и фактическое число hops. Docker bridge и облачный балансировщик не обязательно имеют адрес `127.0.0.1`.

Приложение проверяет исходный `REMOTE_ADDR` прежде, чем применять `ProxyFix`. От остальных клиентов forwarded-заголовки игнорируются. Сам Gunicorn не интерпретирует их повторно: `forwarded_allow_ips` и `secure_scheme_headers` отключены в его конфигурации. Порт backend нельзя оставлять общедоступным в обход настроенного proxy.

Для страниц входа, регистрации, профиля, корзины и callback используется основной Host из `APP_BASE_URL`: это сохраняет cookies и OAuth state на одном домене. HSTS добавляется для HTTPS-запросов. CSRF, CSP с nonce, `HttpOnly`, `SameSite=Lax`, `nosniff` и запрет встраивания применяются ко всему приложению, включая админку.

## Docker

```bash
docker build -t kodee:local .
```

В образ копируются только файлы запуска, зависимости и каталоги приложения `bot/`, `db/`, `web/`. В него не попадают `.env*`, `.local/`, рабочая БД, журналы, резервные копии, ключи и `audit/`. Контейнер работает от UID 10001; исходники и исходные фотографии недоступны ему на запись. БД должна быть доступна **из контейнера**: `127.0.0.1` внутри контейнера — не PostgreSQL на хосте.

Перед запуском контейнера подготовьте env-файл для его сети и постоянное хранилище фотографий. В качестве примера, если PostgreSQL доступен из выбранной Docker-сети и volume с фотографиями уже подготовлен:

```bash
docker run --rm --env-file .env.docker --network YOUR_NETWORK kodee:local \
  python -m flask --app main upgrade-db

docker run --rm --env-file .env.docker --network YOUR_NETWORK kodee:local \
  python -m flask --app main create-admin

docker run --rm --env-file .env.docker --network YOUR_NETWORK \
  -e GUNICORN_BIND=0.0.0.0:5000 -p 127.0.0.1:5000:5000 \
  -v YOUR_IMAGES_VOLUME:/var/data \
  kodee:local
```

Замените имена сети и volume своими. В Docker `PRODUCT_IMAGES_DIR` по умолчанию равен `/var/data/productImgs`; исходные фотографии остаются в образе и используются, пока нет загруженной замены. Для bind mount заранее обеспечьте владельца UID 10001 и право записи. Не монтируйте пустой каталог поверх `web/static/image/productImgs`: он скроет исходные фото. База и её пароль не задаются в Dockerfile.

## Подготовка и деплой на Render с Docker

Локальный `.env.local` на Render не загружается. Там задаются отдельные переменные окружения, отдельный `SECRET_KEY` и отдельный секрет webhook. `DATABASE_URL` берётся из Render Postgres, а не из локальной `kodee_dev`.

### Вариант через Dashboard

1. Подготовьте Render Postgres либо выберите уже существующую базу. Для Web Service в том же аккаунте/регионе используйте **Internal Database URL**. Если это существующая рабочая БД, перед миграцией сохраните резервную копию. Локальные проверки рабочую БД не меняют.
2. Создайте Web Service из репозитория, выберите **Language: Docker** и регион базы. Версия Python и установка зависимостей заданы в `Dockerfile`.
3. **Dockerfile Path:** `./Dockerfile`, **Docker Build Context:** `.`. Отдельный Build Command не нужен.
4. **Docker Command:** оставьте пустым. Render использует `CMD` из Dockerfile: `gunicorn -c gunicorn.conf.py main:app`.
5. **Health Check Path:** `/healthz`.
6. Добавьте переменные ниже через Environment:

```dotenv
DATABASE_URL=INTERNAL_DATABASE_URL_FROM_RENDER
SECRET_KEY=GENERATE_A_NEW_RANDOM_VALUE
ADMIN_EMAIL=YOUR_ADMIN_EMAIL
ADMIN_PASSWORD=YOUR_ADMIN_PASSWORD
SESSION_COOKIE_SECURE=true
PUBLIC_HTTPS=true
TRUSTED_PROXY_CIDRS=
PROXY_X_FOR=0
PROXY_X_PROTO=0
PROXY_X_HOST=0
PROXY_X_PORT=0
WEB_WORKERS=1
BOT_TOKEN=YOUR_BOT_TOKEN
BOT_ALLOWED_USER_IDS=YOUR_NUMERIC_IDS
BOT_WEBHOOK_SECRET=GENERATE_ANOTHER_RANDOM_VALUE
```

Не переносите `KODEE_ENV_FILE=.env.local`, локальный `DATABASE_URL` или `GUNICORN_BIND=127.0.0.1:5000` на Render. Gunicorn по умолчанию слушает `0.0.0.0` и предоставленный платформой `PORT`.

На первом деплое `APP_BASE_URL` можно не задавать: приложение использует Render `RENDER_EXTERNAL_URL`. `TRUSTED_HOSTS` тогда тоже можно оставить пустым — разрешённый hostname выведется из этого адреса. Если подключаете свой домен, задайте явно:

```dotenv
APP_BASE_URL=https://kodee.kz
TRUSTED_HOSTS=kodee.kz,www.kodee.kz,YOUR_SERVICE.onrender.com
```

`PUBLIC_HTTPS=true` предназначен для Render, где публичный TLS завершает платформа. Он не шифрует локальный backend и не является заменой HTTPS на обычном сервере. Здесь IP прокси угадывать не требуется: схема фиксируется настройкой, а forwarded-заголовки клиента не используются.

7. Для постоянных новых фотографий добавьте persistent disk с mount path `/var/data`. Dockerfile уже задаёт следующий путь; в Blueprint он также указан явно:

```dotenv
PRODUCT_IMAGES_DIR=/var/data/productImgs
```

На Render файловая система без диска временная. Persistent disk доступен для платных сервисов; для production нельзя полагаться на сохранение загруженных фотографий после redeploy без такого хранилища. Исходные картинки из репозитория остаются доступны, пока для них нет загруженной замены. На сервисе с диском во время деплоя возможен короткий перерыв в работе.

8. Выполните первый деплой. `/healthz` работает до создания таблиц, но каталог требует подготовленной схемы. В Render Shell затем выполните **осознанно для выбранной базы**:

```bash
python -m flask --app main upgrade-db
python -m flask --app main create-admin
```

Для новой пустой БД можно отдельно заполнить исходный каталог:

```bash
python -m flask --app main seed-products
```

Для существующего рабочего каталога `seed-products` не требуется. Ни миграция, ни создание администратора автоматически при старте сервера не запускаются.

9. Если нужен Google-вход, добавьте `GOOGLE_CLIENT_ID`/`GOOGLE_CLIENT_SECRET` в Environment и новый callback в Google Cloud, например `https://YOUR_SERVICE.onrender.com/callback`. При основном пользовательском домене используйте его `/callback`.
10. Откройте сайт по Render URL, проверьте вход, каталог, фотографии, админку и журналы. Загрузите тестовую фотографию через админку и проверьте, что она сохранилась после перезапуска сервиса. `/healthz` проверяет только работу процесса: ответ 200 ещё не подтверждает подключение к БД и наличие таблиц. После этих проверок переключайте Telegram.

### Переключение Telegram с ngrok на Render

В Environment сервиса задайте:

```dotenv
WEBHOOK_URL=https://YOUR_SERVICE.onrender.com/bot/webhook
```

Если основной домен — `kodee.kz`, используйте `https://kodee.kz/bot/webhook`. Значение `BOT_WEBHOOK_SECRET` должно совпадать с секретом, который передаст команда регистрации, а не с локальным секретом ngrok.

После применения env и перезапуска сервиса выполните в **Render Shell**:

```bash
python -m flask --app main set-bot-webhook
python -m flask --app main bot-status
```

Это переключит тот же бот на Render. Повторно добавлять пользователей в Telegram не нужно; числовые ID должны присутствовать в Render `BOT_ALLOWED_USER_IDS`. После проверки `/start` туннель ngrok и локальный сайт можно остановить.

У одного Telegram-бота один webhook: новый адрес заменяет старый. Локально и на Render могут быть разные секреты — при смене адреса команда передаст секрет выбранного окружения. Чтобы не переключать рабочий бот во время дальнейшей разработки, используйте отдельного тестового бота.

### Необязательный Blueprint

В корне есть `render.yaml`: Docker Web Service `0.5c-512mb` и persistent disk 1 ГиБ. **Это платная конфигурация**, она не применяется автоматически. База не создаётся и не мигрируется: `DATABASE_URL` вводится отдельно. Перед использованием Blueprint проверьте регион относительно своей БД. `APP_BASE_URL`, Google-параметры и финальный `WEBHOOK_URL` задаются после выбора публичного домена.

Документация: [Docker на Render](https://render.com/docs/docker), [переменные Render](https://render.com/docs/environment-variables), [persistent disks](https://render.com/docs/disks).

## Структура проекта

```text
main.py                       точка входа
__init__.py                   фабрика Flask
config.py                     настройки и загрузка env
web/app/routes.py             маршруты сайта
web/app/services/             операции профиля, корзины и каталога
web/app/oauth.py              Google OIDC
web/app/proxy.py              проверка proxy и Host
web/app/security.py           сессии и проверка администратора
web/app/headers.py             CSP и защитные заголовки
web/app/images.py              проверка и публикация фотографий
web/app/admin.py, views.py     Flask-Admin
web/templates/                Jinja-шаблоны
web/static/                   JS, CSS, иконки, фотографии
bot/api/api.py                Telegram webhook
bot/bot/bot.py                создание бота и регистрация обработчиков
bot/services/handlers/        callback и message handlers
bot/services/fsm/             состояния диалогов
db/models.py                 модели SQLAlchemy
db/maintenance.py            команды обслуживания схемы
db/add_products.py           исходный каталог
scripts/local_db.py           отдельная локальная PostgreSQL
scripts/configure_ngrok.py     настройки текущего локального туннеля
render.yaml                   необязательный платный Render Blueprint
tests/                        автоматические проверки
deploy/nginx.conf.example     пример reverse proxy
gunicorn.conf.py              настройки WSGI-сервера
Dockerfile, Procfile          запуск на сервере
```

## Основные маршруты

| Метод и адрес | Назначение / доступ |
|---|---|
| `GET /healthz` | Проверка процесса без обращения к БД |
| `GET /`, `/shop`, `/product/<slug>` | Главная, каталог и активный товар; публично |
| `GET /search?query=...` | Поиск активных товаров; публично |
| `GET /api/products`, `/AllProductJS` | Данные активного каталога; публично |
| `GET /login`, `/register` | Формы входа и регистрации |
| `POST /login/log_user`, `/register/add_user` | Вход и регистрация с CSRF |
| `GET /login/google`, `/callback` | Google OIDC |
| `GET /profil`, `/basket` | Профиль и корзина; нужен вход |
| `POST /profil/update_user`, `/profil/update_password` | Изменение профиля/пароля; вход и CSRF |
| `POST /profil/google/link` | Явная привязка Google; вход и CSRF |
| `POST /profil/add_address`, `/profil/change_address`, `/add_address` | Адреса; вход и CSRF |
| `POST /add_basket`, `/delete_basket`, `/add_favorite` | JSON-операции; вход и CSRF |
| `GET /admin/`, `/admin/panel` | Администрирование |
| `POST /admin/add_imgs` | Фотографии; администратор и CSRF |
| `POST /bot/webhook` | Telegram, проверка отдельного секретного заголовка |
| `GET /contact`, `/individual`, `/help/<theme>` | Информационные страницы |
| `GET /robots.txt`, `/sitemap.xml`, `/.well-known/security.txt` | Служебные публичные файлы |

Для JSON-запросов сайта CSRF-токен передаётся в `X-CSRFToken`; он находится в HTML meta. Для webhook вместо CSRF используется секрет Telegram. Неизвестный или скрытый товар возвращает 404, а не страницу с ошибкой шаблона.

## Проверки

Быстрый набор на SQLite в памяти:

```bash
python -m unittest discover -s tests -v
```

Полный набор на созданной локальной PostgreSQL:

```bash
python scripts/local_db.py test
```

Скрипт сам выбирает `kodee_test` и не трогает `kodee_dev`. Прямой `KODEE_TEST_DATABASE_URL` разрешён только для PostgreSQL на `127.0.0.1`/`localhost` с именем базы `kodee_test`. Тесты намеренно создают и удаляют её таблицы.

Проверяются каталог и гостевые страницы, формы, смена email без подтверждения, сессии, админка, CSRF, фотографии, склад, продажи, сертификаты, webhook, допуск сотрудников, миграции, идемпотентное заполнение каталога и параллельные операции. OAuth проверяется настоящим Authlib с тестовым OIDC-провайдером и подписанными JWT, включая отрицательные сценарии. Proxy-тесты проверяют разрешённые и поддельные Host/forwarded headers.

Вход в настоящий Google-аккаунт требует участия пользователя и зарегистрированного callback. Автоматические тесты не используют реальный Telegram API и не отправляют сообщения сотрудникам.

Дополнительные проверки:

```bash
python -m pip check
python -m pip install pip-audit
pip-audit -r requirements.txt
node --check web/static/js/product.js
```

Папка `audit/` используется для локальных отчётов, результатов Chrome/Docker-проверок и служебных проверочных скриптов. Она не является обязательной частью приложения и не коммитится.

## Журналы и частые проблемы

Журналы приложения: `LOG_DIR/app-<pid>.log`, ошибки: `LOG_DIR/errors-<pid>.log`. Отдельные имена для процессов позволяют им независимо ротировать файлы. Сообщения также идут в stderr; access/error logs Gunicorn доступны в выводе процесса или платформы. События действий записываются как `user_action` с JSON-полями `action`, `source`, `actor_id` и `outcome`: вход и выход, регистрация, профиль, корзина и избранное, изменения через админку и Telegram-бота. Для Telegram `actor_id` — Telegram ID, для сайта — ID пользователя. Записываются идентификаторы объектов и отдельные параметры операции, но не пароли, токены или содержимое форм. Файлы локальны для процесса и могут исчезнуть при пересоздании контейнера; для длительного хранения собирайте stderr внешней системой журналирования.

| Симптом | Что проверить |
|---|---|
| `SECRET_KEY и DATABASE_URL` не заданы | Правильный env-файл и `KODEE_ENV_FILE` |
| Подключение к локальной PostgreSQL не удалось | `python scripts/local_db.py status`, порт 55439 и локальный env |
| Схема/`google_sub` отсутствует | Выполнить `upgrade-db` для выбранной локальной БД |
| 400 при открытии сайта | `TRUSTED_HOSTS` и Host после proxy |
| Вход не сохраняется на локальном HTTP | `SESSION_COOKIE_SECURE=false` и одинаковый адрес в браузере/`APP_BASE_URL` |
| Google `redirect_uri_mismatch` | Точный URI в Google Console, включая схему, hostname, порт и `/callback` |
| Google state/nonce не совпал | Повторить вход с основного адреса, проверить cookies и единый `SECRET_KEY` у workers |
| Email Google уже занят | Войти в существующий профиль и явно привязать Google |
| Webhook 403 | Совпадение `BOT_WEBHOOK_SECRET` у приложения и установленного webhook |
| Webhook 503 | `BOT_TOKEN` и достаточная длина секрета |
| Бот не реагирует сотруднику | Числовой user ID в `BOT_ALLOWED_USER_IDS`, личный чат, перезапуск приложения |
| Фотографии пропали после Docker-деплоя | Содержимое и права постоянного volume |
| Миграция остановилась на дубликатах | Разобрать указанные записи до повторного запуска |

Проверять рабочую схему, менять webhook рабочего бота или применять команды миграции следует отдельно от локальных проверок. Локальная база создаётся без копирования данных пользователей из production.

## Текущие упрощения

Смена email доступна без письма-подтверждения. Повторный ввод текущего пароля, массовый отзыв сессий и rate limiting пока не добавлены. Сертификаты используют намеренно упрощённые правила. Заказы отправляются через WhatsApp, онлайн-оплаты нет.

## Документация используемых протоколов

- [Flask: reverse proxy](https://flask.palletsprojects.com/en/stable/deploying/proxy_fix/)
- [Flask: проверка Host](https://flask.palletsprojects.com/en/stable/web-security/)
- [Authlib: Flask OAuth/OIDC](https://docs.authlib.org/en/latest/oauth2/client/web/flask.html)
- [Google: OpenID Connect](https://developers.google.com/identity/openid-connect/openid-connect)
- [Telegram: setWebhook](https://core.telegram.org/bots/api#setwebhook)
