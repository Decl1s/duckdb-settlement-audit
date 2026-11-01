"""Я проверяю весь снимок до SQL, включая будущие записи и дубли."""
import csv
from datetime import date
import hashlib
import io
from pathlib import Path
import re

ORDER_FIELDS = ['order_id', 'currency', 'expected_minor', 'ordered_on']
PAYMENT_FIELDS = ['payment_id', 'order_id', 'currency', 'amount_minor', 'kind', 'settled_on']
MAX_BYTES = 8 * 1024 * 1024
MAX_ROWS = 100_000
MAX_AMOUNT = 10**12


class ContractError(ValueError):
    """Я отделяю отказ контракта от программной ошибки."""


def iso_day(value):
    # Я требую календарную дату без времени; сравнение DATE не зависит от timezone.
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
        raise ContractError('Я ожидаю дату YYYY-MM-DD')
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise ContractError('Я получил невозможную дату') from None


def read_csv(path, fields):
    """Я читаю ограниченный immutable bytes-снимок; SHA относится к тем же байтам."""
    with Path(path).open('rb') as source:
        raw = source.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ContractError('Я ограничил каждый CSV восемью MiB')
    try:
        text = raw.decode('utf-8-sig')
        reader = csv.reader(io.StringIO(text, newline=''), strict=True)
        if next(reader, None) != fields:
            raise ContractError('Я ожидаю точный заголовок CSV и порядок полей')
        rows = []
        for index, row in enumerate(reader, 2):
            if len(rows) >= MAX_ROWS:
                raise ContractError('Я ограничил CSV ста тысячами строк')
            if len(row) != len(fields):
                raise ContractError(f'Я получил неверное число полей, строка {index}')
            rows.append(tuple(row))
    except (UnicodeError, csv.Error):
        raise ContractError('Я не прочитал корректный UTF-8 CSV') from None
    return rows, hashlib.sha256(raw).hexdigest()


def identifier(value):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}', value):
        raise ContractError('Я ожидаю идентификатор из букв ASCII, цифр, _ или -')
    return value


def currency(value):
    if not re.fullmatch(r'[A-Z]{3}', value):
        raise ContractError('Я ожидаю валюту из трёх заглавных букв ASCII')
    return value


def amount(value, *, zero):
    if not re.fullmatch(r'0|[1-9][0-9]{0,12}', value):
        raise ContractError('Я ожидаю целую сумму в minor units без знака и пробелов')
    result = int(value)
    if result > MAX_AMOUNT or (result == 0 and not zero):
        raise ContractError('Я получил сумму вне контракта')
    return result


def load(orders_path, payments_path):
    orders_raw, orders_sha = read_csv(orders_path, ORDER_FIELDS)
    payments_raw, payments_sha = read_csv(payments_path, PAYMENT_FIELDS)
    orders, payments, seen_orders, seen_payments = [], [], set(), {}
    for key, curr, total, day in orders_raw:
        row = (identifier(key), currency(curr), amount(total, zero=True), iso_day(day))
        if key in seen_orders:
            raise ContractError('Я запретил повтор order_id даже при одинаковых полях')
        seen_orders.add(key)
        orders.append(row)
    for pid, oid, curr, total, kind, day in payments_raw:
        if kind not in ('capture', 'refund'):
            raise ContractError('Я ожидаю kind capture или refund')
        row = (identifier(pid), identifier(oid), currency(curr), amount(total, zero=False), kind, iso_day(day))
        previous = seen_payments.get(pid)
        if previous is not None and previous != row:
            raise ContractError('Я обнаружил конфликт payment_id; победителя не выбираю')
        if previous is None:
            seen_payments[pid] = row
            payments.append(row)
    return orders, payments, {
        'orders_sha256': orders_sha, 'payments_sha256': payments_sha,
        'orders_raw': len(orders_raw), 'payments_raw': len(payments_raw),
        'payments_unique': len(payments), 'payment_duplicates': len(payments_raw) - len(payments),
    }
