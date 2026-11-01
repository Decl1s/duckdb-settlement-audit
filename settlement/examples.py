"""Я создаю воспроизводимые учебные строки без реальных заказов и контактов."""
import csv
from pathlib import Path
from .contracts import ORDER_FIELDS, PAYMENT_FIELDS


def data():
    orders = [
        ('O100', 'RUB', 10000, '2026-11-01'), ('O200', 'RUB', 5000, '2026-11-01'),
        ('O300', 'USD', 2000, '2026-11-01'), ('O400', 'RUB', 3000, '2026-11-01'),
        ('O500', 'RUB', 7000, '2026-11-01'), ('O600', 'RUB', 0, '2026-11-01'),
        ('O700', 'RUB', 1001, '2026-11-01'), ('O800', 'RUB', 900, '2026-11-02'),
    ]
    payments = [
        ('P1', 'O100', 'RUB', 6000, 'capture', '2026-11-01'),
        ('P2', 'O100', 'RUB', 4000, 'capture', '2026-11-01'),
        ('P2', 'O100', 'RUB', 4000, 'capture', '2026-11-01'),
        ('P3', 'O200', 'RUB', 5000, 'capture', '2026-11-01'),
        ('P4', 'O200', 'RUB', 1000, 'refund', '2026-11-01'),
        ('P5', 'O300', 'USD', 2500, 'capture', '2026-11-01'),
        ('P6', 'O999', 'RUB', 200, 'capture', '2026-11-01'),
        ('P7', 'O500', 'USD', 7000, 'capture', '2026-11-01'),
        ('P8', 'O700', 'RUB', 1000, 'capture', '2026-11-01'),
        ('P9', 'O400', 'RUB', 3000, 'capture', '2026-11-02'),
    ]
    return orders, payments


def write_csv(path, fields, rows):
    with Path(path).open('x', encoding='utf-8', newline='') as dest:
        writer = csv.writer(dest, lineterminator='\n')
        writer.writerow(fields)
        writer.writerows(rows)


def prepare(out):
    target = Path(out)
    target.mkdir(parents=True, exist_ok=False)
    orders, payments = data()
    write_csv(target / 'orders.csv', ORDER_FIELDS, orders)
    write_csv(target / 'payments.csv', PAYMENT_FIELDS, payments)
    return {'orders': len(orders), 'payments': len(payments)}
