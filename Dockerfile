FROM python:3.14-slim

WORKDIR /kodee

# Обновляем системные сертификаты
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && update-ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Устанавливаем Python-зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir --upgrade "certifi>=2026.10.19"

COPY . .

ENV FLASK_APP=main.py

CMD ["python", "main.py"]



# FROM python:3.14-slim

# WORKDIR /kodee

# COPY requirements.txt .

# RUN pip install -r requirements.txt

# COPY . .

# ENV FLASK_APP=main.py

# CMD ["python", "main.py"]


# services:
#   web:
#     build: .
# 
#     ports:
#       - 5000:5000
# 
#     depends_on:
#       - postgres
# 
#     env_file:
#       - .env
# 
#     environment:
#       ADMIN_EMAIL: ${ADMIN_EMAIL}
#       ADMIN_PASSWORD: ${ADMIN_PASSWORD}
#       DATABASE_URL: ${DATABASE_URL}
#       FLASK_ENV: ${FLASK_ENV}
#       SECRET_KEY: ${SECRET_KEY}
# #GOOGLE_CLIEND_ID=
# #GOOGLE_CLIENT_SECRET=
# 
#     volumes:
#       - .:/kodee
# 
#     command: flask run --host 0.0.0.0
# 
#   postgres:
#     image: postgres:18.4
# 
#     env_file:
#      - .env
# 
#     environment:
#       POSTGRES_USER: ${POSTGRES_USER}
#       POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
#       POSTGRES_DB: ${POSTGRES_DB}
# 
#     volumes:
#       - postgres_data:/var/lib/postgresql
# 
# volumes:
#   postgres_data: