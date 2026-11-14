"""Validation shared by web forms and bot product operations."""
import math
from email_validator import validate_email, EmailNotValidError


def text(value, label, maximum, required=True):
    if not isinstance(value, str):
        raise ValueError(f"Некорректное поле: {label}")
    value = value.strip()
    if (required and not value) or len(value) > maximum or any(ord(c) < 32 and c not in '\n\r\t' for c in value):
        raise ValueError(f"Проверьте поле {label} (до {maximum} символов)")
    return value


def email(value):
    value = text(value, 'Email', 75).lower()
    try:
        return validate_email(value, check_deliverability=False).normalized.lower()
    except EmailNotValidError:
        raise ValueError('Некорректный Email') from None


def positive_id(value):
    if isinstance(value, bool) or not isinstance(value, (str, int)) or not str(value).isdigit():
        raise ValueError('Некорректный ID')
    value = int(value)
    if not 0 < value <= 2147483647:
        raise ValueError('Некорректный ID')
    return value


PRODUCT_FIELDS = {'name': 100, 'short_name': 100, 'concept': 50, 'category': 50, 'descriptions': 510}
STOCK_FIELDS = frozenset({'gold', 'silver', 'form_gold', 'form_silver'})


def product_value(field, value):
    if field in PRODUCT_FIELDS:
        return text(value, field, PRODUCT_FIELDS[field])
    if field not in {'price', 'price_chet', 'weight', 'G'}:
        raise ValueError('Недопустимое поле товара')
    try:
        result = float(value) if field == 'weight' else int(value)
    except (ValueError, TypeError, OverflowError):
        raise ValueError('Введите корректное число') from None
    if not math.isfinite(result) or result < 0 or result > 2147483647:
        raise ValueError('Число должно быть от 0 до 2147483647')
    return result
