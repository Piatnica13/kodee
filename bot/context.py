from dataclasses import dataclass

from flask import Flask
from telebot import TeleBot

from db.models import db

from .services.user_service import UserService
from .services.product_service import ProductService
from .services.notification_service import NotificationService
from .services.markup_service import MarkupService
from .services.fsm.fsm_storage import FSM


@dataclass
class BotContext:

    bot: TeleBot

    app: Flask

    db: db # type: ignore

    fsm: FSM

    markup: MarkupService

    users: UserService

    products: ProductService

    notifications: NotificationService