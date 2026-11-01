# Какие технологии я использую

01.11.2026 · 0.1.0. После Polars я выбрал встроенный аналитический SQL: новое
умение здесь — контроль зерна и FULL OUTER JOIN двух неодинаковых источников.

| Компонент | Фактическая версия | Для чего и почему я использую | Официальный источник |
| --- | --- | --- | --- |
| CPython | Локально 3.14.4; CI target 3.14.10; минимум 3.11 | Я связываю локальные CSV, DuckDB и CLI без web-framework | [3.14](https://docs.python.org/3.14/), [3.14.10](https://www.python.org/downloads/release/python-31410/) |
| duckdb | 2.0.0 LTS | Я выполняю аналитический SQL и typed Parquet без сервера | [PyPI exact release](https://pypi.org/project/duckdb/2.0.0/), [документация 2.0](https://duckdb.org/docs/2.0/) |
| SQL DuckDB | Входит в 2.0.0 | Я использую CTE, CASE, GROUP BY, SUM, FULL OUTER JOIN, COALESCE, BIGINT и DATE | [JOIN](https://duckdb.org/docs/2.0/sql/query_syntax/from), [aggregates](https://duckdb.org/docs/2.0/sql/functions/aggregates) |
| Parquet + Zstandard | Входит в wheel DuckDB 2.0.0 | Я сохраняю типы и сжатие без pyarrow | [Parquet](https://duckdb.org/docs/2.0/data/parquet/overview) |
| csv/io/datetime/re | stdlib Python | Я проверяю header, ширину, UTF-8, даты, ID и точные целые | [csv](https://docs.python.org/3.14/library/csv.html), [datetime](https://docs.python.org/3.14/library/datetime.html) |
| argparse/json/pathlib/sys/contextlib | stdlib Python | Я задаю CLI, JSON и закрываю ресурсы | [stdlib](https://docs.python.org/3.14/library/) |
| hashlib/os/tempfile/shutil | stdlib Python | Я фиксирую SHA-256, stage, exclusive lock и rename | [os](https://docs.python.org/3.14/library/os.html), [hashlib](https://docs.python.org/3.14/library/hashlib.html) |
| unittest/mock/random/subprocess | stdlib Python | Я проверяю бизнес-примеры, независимый oracle, отказы и настоящий CLI | [unittest](https://docs.python.org/3.14/library/unittest.html) |
| zipfile/urllib | stdlib Python | Я собираю deterministic ZIP и публикую его только в CI | [zipfile](https://docs.python.org/3.14/library/zipfile.html), [urllib](https://docs.python.org/3.14/library/urllib.request.html) |
| uv | 0.13.1 локально | Я разрешил единственную зависимость и установил hash-lock в .venv | [uv](https://docs.astral.sh/uv/) |
| pip/venv | pip patch зависит от среды; venv stdlib | Я описал простой запуск с --require-hashes и --only-binary | [secure installs](https://pip.pypa.io/en/stable/topics/secure-installs/) |
| Git, Markdown, JSON, TOML, YAML | Git/text formats | Я веду собственный репозиторий, allowlist, документы и workflow | [Git](https://git-scm.com/docs), [Actions](https://docs.github.com/en/actions) |
| VS Code + Python extension | Необязательные; версию не закрепляю | Я подготовил четыре задачи запуска и карту файлов | [tasks](https://code.visualstudio.com/docs/editor/tasks) |

Я закрепил duckdb==2.0.0 одновременно в requirements.in и pyproject.toml.
В requirements.lock я зафиксировал hashes официальных артефактов; в окружении
нет дополнительных Python-транзитивных dependencies. Нативный движок и кодеки
входят в wheel; отдельные версии его встроенных компонентов я не измерял.
Автоматическую установку/загрузку extensions я отключил. После установки
зависимости вычислению не нужна сеть.

В Actions я закрепил checkout v7.0.1:
`3d3c42e5aac5ba805825da76410c181273ba90b1` и setup-python v7.1.0:
`6d4fd22b20465ccc0f7354476588e8df7c9ca0e0`. Я выбрал ubuntu-24.04 и windows-2025;
образы управляются GitHub. Обычные проверки имеют contents:read, отдельный
release job после обеих ОС получает contents:write. Я не сохраняю CI-токен
в файлах. Реальные результаты и версии из логов я фиксирую отдельно в VALIDATION
и локальной квитанции серии; наличие workflow не называю пройденным CI.
