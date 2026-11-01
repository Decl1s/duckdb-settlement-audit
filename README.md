# Моя сверка заказов и платежей на DuckDB

Я сделал учебный инструмент для ежедневной сверки двух CSV. Я показываю, какие
заказы оплачены, где есть недоплата или переплата, где отсутствует платёж, а где
платёж существует без заказа. Я использую только воспроизводимые синтетические данные.

Новый навык — **агрегирование до FULL OUTER JOIN с сохранением зерна и валюты**.
Я вынес бизнес-вычисления в [один SQL](sql/reconcile.sql). Для чтения кода я начинаю
с [START_HERE](START_HERE.md), для подробного объяснения — с [NOTES](NOTES.md).

## Как я запускаю за 5–10 минут

Я использую Python 3.11+; локально я проверил 3.14.4. CI закреплён на 3.14.10.
Я создаю отдельное окружение, ничего глобально не устанавливаю:

```bash
python -m venv .venv
```

В Linux/macOS я активирую `source .venv/bin/activate`, в PowerShell —
`.venv\Scripts\Activate.ps1`. Если activation запрещён политикой PowerShell,
я использую `.venv\Scripts\python.exe` вместо `python` в командах ниже.
macOS я отдельно не проверял.

```bash
python -m pip install --require-hashes --only-binary :all: -r requirements.lock
python -m settlement prepare --out workspace/input
python -m settlement run --orders workspace/input/orders.csv --payments workspace/input/payments.csv --out workspace/report --as-of 2026-11-01
python -m settlement inspect --out workspace/report
```

Я получаю 8 заказов и 10 строк платежей на входе. Один платёж повторяется,
один заказ и один уникальный платёж относятся к следующему дню.
В отчёте я ожидаю **9 строк и 7 расхождений**:

| status | Строки | Что я показываю |
| --- | ---: | --- |
| matched | 2 | O100 оплачен двумя частями; O600 бесплатный |
| missing_payment | 2 | O400 и O500 RUB без платежа на выбранную дату |
| underpaid | 2 | O200 после возврата; O700 отличается на 1 minor unit |
| overpaid | 1 | O300 USD переплачен на 500 |
| orphan_payment | 2 | O999 без заказа; O500 USD с несовпадающей валютой |

Я никогда не суммирую разные валюты в общую «денежную» метрику:

| Валюта | expected_minor | net_minor | delta_minor |
| --- | ---: | ---: | ---: |
| RUB | 26001 | 15200 | -10801 |
| USD | 2000 | 9500 | 7500 |

## Что я сохраняю

В `workspace/report/` я открываю `reconciliation.csv` для чтения,
`reconciliation.parquet` для аналитики и `summary.json` для счётчиков,
параметров и SHA-256 входных/выходных байтов. `inspect` сверяет хеши отчётов.
SHA обнаруживает порчу при неизменном manifest; цифровую подпись я не реализовал.

Я передаю `--as-of YYYY-MM-DD` явно: дата включительна. Через
`--tolerance-minor 1` я разрешаю отклонение на 1 единицу, сохраняя настоящее
значение `delta_minor`. Для каждого эксперимента я задаю **новый `--out`**;
существующий результат и подготовленные CSV я не заменяю.

```bash
python -m settlement run --orders workspace/input/orders.csv --payments workspace/input/payments.csv --out workspace/tolerance1 --as-of 2026-11-01 --tolerance-minor 1
python -m settlement inspect --out workspace/tolerance1
python -m unittest discover -s tests -v
python scripts/ci.py
```

В варианте с допуском я ожидаю 6 расхождений и 3 matched. В `ci.py` я выполняю
20 unit-сценариев, настоящий CLI, повторы, отказ при занятом результате,
контролируемый сбой, пять заданий и проверку повторяемого source ZIP.
Фактическую среду и ограничения я записал в [VALIDATION](VALIDATION.md).

## Какие границы я задал

Я принимаю точные заголовки из [CONCEPT](CONCEPT.md), UTF-8 CSV до 8 MiB и
100000 строк на файл. Я отклоняю некорректную строку целиком вместе с запуском,
конфликтующие payment_id и любые повторные order_id. Совпадающий повтор платежа
я считаю один раз. Суммы я храню целыми minor units, возврат вычитаю из capture.
FX, комиссии, авторизации, выплаты банка и соответствие возврата исходному capture
в этой маленькой модели я не реализовал.

Я публикую каталог через staging + rename под lock-файлом для cooperating writers.
После обычной ошибки я убираю stage/lock; после kill или power loss они могут
остаться. В [NOTES](NOTES.md) я описал осмотр и восстановление. fsync-гарантию,
враждебные filesystem races и сетевую файловую систему я не проверял.

Мои материалы: [замысел](CONCEPT.md), [технологии и версии](TECHNOLOGIES.md),
[карта кода](START_HERE.md), [подробный конспект и задания](NOTES.md),
[проверки](VALIDATION.md). Выпуск: [v0.1.0](https://github.com/Decl1s/duckdb-settlement-audit/releases/tag/v0.1.0).
