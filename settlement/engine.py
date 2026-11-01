"""Я оставляю предметные вычисления в SQL, а файловые границы — в Python."""
from contextlib import closing
import csv
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile

import duckdb
from .contracts import ContractError, iso_day, load

ROOT = Path(__file__).resolve().parents[1]
STATUSES = ('matched', 'missing_payment', 'underpaid', 'overpaid', 'orphan_payment')
REPORT_FILES = ('reconciliation.parquet', 'reconciliation.csv')


def connect():
    # Я отключаю автоматическую загрузку extensions; сервер и сеть мне не нужны.
    return duckdb.connect(':memory:', config={
        'autoinstall_known_extensions': 'false', 'autoload_known_extensions': 'false',
        'threads': '1', 'memory_limit': '256MB',
    })


def calculate(orders_path, payments_path, as_of, tolerance=0):
    """Я возвращаю зерно (order_id,currency), метрики и SHA входных bytes."""
    day = iso_day(as_of)
    if type(tolerance) is not int or not 0 <= tolerance <= 10**9:
        raise ContractError('Я ограничил tolerance диапазоном 0..1000000000')
    orders, payments, provenance = load(orders_path, payments_path)
    with closing(connect()) as con:
        con.execute('CREATE TABLE orders(order_id VARCHAR, currency VARCHAR, expected_minor BIGINT, ordered_on DATE)')
        con.execute('CREATE TABLE payments(payment_id VARCHAR, order_id VARCHAR, currency VARCHAR, amount_minor BIGINT, kind VARCHAR, settled_on DATE)')
        if orders:
            con.executemany('INSERT INTO orders VALUES (?,?,?,?)', orders)
        if payments:
            con.executemany('INSERT INTO payments VALUES (?,?,?,?,?,?)', payments)
        sql = (ROOT / 'sql/reconcile.sql').read_text(encoding='utf-8')
        cursor = con.execute(sql, {'as_of': day, 'tolerance': tolerance})
        columns = [item[0] for item in cursor.description]
        rows = [dict(zip(columns, values)) for values in cursor.fetchall()]
    counts = {status: sum(row['status'] == status for row in rows) for status in STATUSES}
    by_currency = []
    for curr in sorted({row['currency'] for row in rows}):
        subset = [row for row in rows if row['currency'] == curr]
        by_currency.append({'currency': curr, **{
            field: sum(row[field] for row in subset)
            for field in ['expected_minor', 'captured_minor', 'refunded_minor', 'net_minor', 'delta_minor']
        }})
    summary = {
        'schema_version': 1, 'as_of': as_of, 'tolerance_minor': tolerance,
        'engine': duckdb.__version__, 'input': provenance,
        'excluded_future': {'orders': sum(row[3] > day for row in orders), 'payments': sum(row[5] > day for row in payments)},
        'rows': len(rows), 'issues': len(rows) - counts['matched'], 'statuses': counts,
        'by_currency': by_currency,
    }
    return rows, summary


def write_reports(stage, rows):
    """Я сохраняю типы даже для пустого отчёта; путь передаю параметром."""
    with closing(connect()) as con:
        con.execute('''CREATE TABLE report(order_id VARCHAR, currency VARCHAR, has_order BOOLEAN,
            payment_count BIGINT, expected_minor BIGINT, captured_minor BIGINT, refunded_minor BIGINT,
            net_minor BIGINT, delta_minor BIGINT, status VARCHAR)''')
        if rows:
            con.executemany('INSERT INTO report VALUES (?,?,?,?,?,?,?,?,?,?)', [tuple(row.values()) for row in rows])
        con.execute("COPY (SELECT * FROM report ORDER BY order_id,currency) TO ? (FORMAT PARQUET, COMPRESSION ZSTD)", [str(stage / REPORT_FILES[0])])
    fields = ['order_id', 'currency', 'has_order', 'payment_count', 'expected_minor', 'captured_minor', 'refunded_minor', 'net_minor', 'delta_minor', 'status']
    with (stage / REPORT_FILES[1]).open('w', encoding='utf-8', newline='') as dest:
        writer = csv.DictWriter(dest, fieldnames=fields, lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)


def run(orders, payments, out, as_of, tolerance=0, *, fail_before_publish=False):
    """Я публикую новый каталог одним rename под эксклюзивным lock для своих writers."""
    target = Path(out).absolute()
    target.parent.mkdir(parents=True, exist_ok=True)
    lock = target.with_name(target.name + '.lock')
    # Я не удаляю чужой lock: после настоящего kill восстановление требует осмотра.
    with lock.open('x', encoding='ascii') as handle:
        handle.write(str(os.getpid()))
    stage = None
    try:
        if target.exists() or target.is_symlink():
            raise FileExistsError('Я сохраняю существующий результат; нужен новый --out')
        rows, summary = calculate(orders, payments, as_of, tolerance)
        stage = Path(tempfile.mkdtemp(prefix='.settlement-stage-', dir=target.parent))
        write_reports(stage, rows)
        summary['files'] = {name: hashlib.sha256((stage / name).read_bytes()).hexdigest() for name in REPORT_FILES}
        (stage / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        # Я проверяю read-back перед публикацией и сохраняю failpoint для демонстрации.
        if inspect(stage)['preview'] != rows:
            raise RuntimeError('Я не подтвердил Parquet read-back')
        if fail_before_publish:
            raise RuntimeError('Я остановился перед публикацией по failpoint')
        if target.exists() or target.is_symlink():
            raise FileExistsError('Я обнаружил занятый --out')
        stage.rename(target)
        stage = None
        return summary
    finally:
        if stage is not None:
            shutil.rmtree(stage)
        lock.unlink()


def inspect(out):
    """Я сверяю SHA и возвращаю отчёт. SHA обнаруживает порчу, но не доказывает автора."""
    folder = Path(out)
    summary = json.loads((folder / 'summary.json').read_text(encoding='utf-8'))
    if summary.get('schema_version') != 1 or set(summary.get('files', {})) != set(REPORT_FILES):
        raise ContractError('Я не распознал контракт summary')
    for name in REPORT_FILES:
        if hashlib.sha256((folder / name).read_bytes()).hexdigest() != summary['files'][name]:
            raise ContractError('Я обнаружил повреждение отчёта')
    with closing(connect()) as con:
        cur = con.execute('SELECT * FROM read_parquet(?) ORDER BY order_id,currency', [str(folder / REPORT_FILES[0])])
        rows = [dict(zip([item[0] for item in cur.description], values)) for values in cur.fetchall()]
    if len(rows) != summary['rows']:
        raise ContractError('Я получил другое количество строк')
    return {'summary': summary, 'preview': rows}
