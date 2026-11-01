"""Я даю три команды: prepare, run, inspect; stdout JSON, ошибки stderr, код 2."""
import argparse
import json
import sys
import duckdb
from .engine import inspect, run
from .examples import prepare


def main():
    parser = argparse.ArgumentParser(description='Моя локальная SQL-сверка заказов и платежей')
    sub = parser.add_subparsers(dest='command', required=True)
    demo = sub.add_parser('prepare', help='Я создаю редактируемые синтетические CSV')
    demo.add_argument('--out', required=True)
    job = sub.add_parser('run', help='Я сохраняю новый согласованный отчёт')
    for flag in ['orders', 'payments', 'out', 'as-of']:
        job.add_argument('--' + flag, required=True)
    job.add_argument('--tolerance-minor', type=int, default=0)
    job.add_argument('--fail-before-publish', action='store_true', help='Я демонстрирую контролируемый сбой')
    view = sub.add_parser('inspect', help='Я проверяю целостность и показываю все строки')
    view.add_argument('--out', required=True)
    args = parser.parse_args()
    try:
        if args.command == 'prepare':
            result = prepare(args.out)
        elif args.command == 'inspect':
            result = inspect(args.out)
        else:
            result = run(args.orders, args.payments, args.out, args.as_of, args.tolerance_minor, fail_before_publish=args.fail_before_publish)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except (OSError, ValueError, RuntimeError, duckdb.Error) as error:
        # Я не печатаю содержимое входных строк и traceback для ожидаемого отказа.
        print('Я остановил обработку: ' + str(error), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
