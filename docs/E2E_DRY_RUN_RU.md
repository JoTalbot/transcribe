# Dry-run Oracle → Exchange → Colab

## Назначение

Этот сценарий проверяет полный контракт обмена без GPU, пользовательского production-аудио и реального Colab inference.

## 1. Oracle / PostgreSQL

На Oracle ARM должен быть доступен `TRANSCRIBE_DATABASE_URL` и каталог exchange, общий с Colab/Drive.

Инициализация очереди выполняется через:

```bash
python scripts/run_pipeline.py --manifest state/manifest.json
```

Проверить, что запись и stage jobs появились в PostgreSQL.

## 2. Dispatch

Для тестовой записи:

```bash
python scripts/submit_exchange_jobs.py \
  --manifest state/manifest.json \
  --exchange exchange \
  --recording <recording_id> \
  --worker oracle-dry-run
```

Ожидаемый результат: request появляется в `exchange/requests/`, а PostgreSQL job получает `running`, `worker=oracle-dry-run` и непустой `lease_id`.

## 3. Colab-side protocol test

Без загрузки моделей можно проверить exchange contract тестовым processor:

```python
from pathlib import Path
from scripts.colab_exchange_worker import process_one, dry_run_processor
from transcribe_intelligence.exchange import FileExchange

exchange = FileExchange(Path("exchange"))
for request in exchange.list_requests():
    print(process_one(exchange, request.stem, dry_run_processor))
```

После этого request должен исчезнуть из `requests/` и `processing/`, а соответствующий JSON result появиться в `results/`.

## 4. Apply result

На Oracle:

```bash
python scripts/oracle_worker.py \
  --manifest state/manifest.json \
  --exchange exchange \
  --database-url "$TRANSCRIBE_DATABASE_URL" \
  --worker oracle-dry-run \
  --once
```

Ожидается, что результат с теми же `worker + lease_id` будет принят PostgreSQL и следующий зависимый stage станет доступен для dispatch.

## 5. Важное ограничение

`dry_run_processor` подтверждает только transport/lease/result contract. Он **не подтверждает** работу Whisper, Pyannote, CUDA или Google Colab.

Реальный GPU gate выполняется отдельно на Colab с тестовым аудиофайлом. Production-аудио до успешного dry-run использовать нельзя.
