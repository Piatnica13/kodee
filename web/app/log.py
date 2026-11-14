import logging
import json
from logging.handlers import RotatingFileHandler
import os

class StatusCodeFilter(logging.Filter):
    """Фильтр для исключения 200 и 304 статусов"""
    def filter(self, record):
        message = record.getMessage()
        return not (' 200 ' in message or ' 304 ' in message)

def setup_logging(app):
    """Настройка логирования:
    - В терминал: все кроме 200/304
    - В файл: WARNING и выше (без INFO)
    """
    
    # Создаем папку для логов
    log_dir = app.config.get("LOG_DIR", "logs")
    os.makedirs(log_dir, exist_ok=True)

    # Общий формат логов
    log_format = "[%(asctime)s] %(levelname)s: %(message)s [in %(module)s]"

    # --- 1. Настройка записи в ФАЙЛ (WARNING и выше) ---
    file_handler_errors = RotatingFileHandler(
        filename=os.path.join(log_dir, f"errors-{os.getpid()}.log"),
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=5,
        encoding="utf-8"
    )
    file_handler_errors.setLevel(logging.WARNING)  # Только WARNING и выше
    file_handler_errors.setFormatter(logging.Formatter(log_format))

    # --- 1.5. Настройка записи в ФАЙЛ (INFO и выше) ---


    file_handler_app = RotatingFileHandler(
        filename=os.path.join(log_dir, f"app-{os.getpid()}.log"),
        maxBytes=10*1024*1024,
        backupCount=5,
        encoding="utf-8"
    )
    file_handler_app.setLevel(logging.INFO)
    file_handler_app.setFormatter(logging.Formatter(log_format))

    # --- 2. Настройка вывода в ТЕРМИНАЛ (INFO и выше, но без 200/304) ---
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(logging.Formatter(log_format))
    console_handler.addFilter(StatusCodeFilter())  # Применяем фильтр

    # --- Настройка логгеров ---
    
    # Удаляем стандартные обработчики
    for handler in list(app.logger.handlers):
        app.logger.removeHandler(handler)
        handler.close()
    
    # Добавляем наши обработчики
    app.logger.addHandler(file_handler_errors)
    app.logger.addHandler(file_handler_app)
    app.logger.addHandler(console_handler)
    app.logger.propagate = False
    app.logger.setLevel(logging.INFO)  # Минимальный уровень

    # Настройка Werkzeug для вывода в терминал (с фильтром)
    werkzeug_logger = logging.getLogger('werkzeug')
    werkzeug_logger.handlers.clear()
    werkzeug_logger.addHandler(console_handler)
    werkzeug_logger.setLevel(logging.INFO)

def log_action(action, *, actor_id=None, source="web", outcome="success", **details):
    """Write a structured event without collecting request bodies or credentials."""
    from flask import current_app, g, has_request_context, session
    if actor_id is None and source == "web" and has_request_context():
        actor_id = session.get("user_id")
    if actor_id is None and source == "telegram":
        actor_id = g.get("telegram_actor_id")
    event = {"action": action, "source": source, "actor_id": actor_id,
             "outcome": outcome, **details}
    current_app.logger.info("user_action %s", json.dumps(event, ensure_ascii=False, sort_keys=True))
