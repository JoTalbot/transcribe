# Статус проекта Transcribe

Дата проверки: 2026-09-15

## Текущее состояние

Ядро распределённого execution pipeline доведено до устойчивого PostgreSQL/lease/exchange уровня, но **полный 9-стадийный production E2E ещё не готов**. Основной оставшийся блокер теперь точно локализован: queue contract содержит 9 стадий, тогда как реальный Colab exchange worker умеет выполнять только ASR и diarization (embeddings обрабатываются отдельной веткой worker). Поэтому нельзя честно объявлять Oracle → Colab → полный pipeline production-ready. Человечество снова придумало интерфейс шире реализации.

### Проверено и усилено

- PostgreSQL используется как каноническое состояние execution jobs.
- Захват задания защищён транзакционным lease-механизмом.
- Два конкурентных worker-процесса не должны получить одно и то же задание.
- `worker + lease_id` обязательны для heartbeat, completion и failure.
- Просроченный lease может быть переотдан другому worker.
- Старый worker не может завершить уже переотданное задание.
- Просроченный lease переводится в `retry`, а при достижении лимита попыток в `failed`.
- PostgreSQL integration test покрывает dispatch → lease → reclaim → stale-result quarantine → принятие результата нового worker.
- Scheduler для DB-backed repository использует транзакционный `recover_stale()`.
- Colab worker не оставляет malformed claim в `processing`: такой request отправляется в quarantine.
- Production bootstrap очереди больше не пишет `state/jobs.json`: `scripts/run_pipeline.py` создаёт recordings и stable stage jobs непосредственно в PostgreSQL.
- `scripts/submit_exchange_jobs.py` работает через PostgreSQL + `Scheduler`/`ExchangeCoordinator` и не создаёт production exchange jobs через legacy `JobStore`.
- `scripts/apply_exchange_results.py` применяет результаты через PostgreSQL lease ownership.
- `scripts/oracle_worker.py` использует свежий PostgreSQL connection на цикл, применяет результаты, reclaim просроченных lease и dispatch через `Scheduler`/`ExchangeCoordinator`.
- Oracle daemon переживает временный сбой одного цикла и продолжает работу.
- Colab exchange worker очищает `processing` marker даже при неудаче публикации результата.
- Добавлен dry-run контракт Oracle → exchange без GPU и production audio.
- README синхронизирован с новым Oracle daemon entrypoint.

## Последние исправления

1. Убрана зависимость integration tests от фиксированных задержек истечения lease: reclaim проверяется bounded polling и тестовым временем/SQL.
2. Добавлен PostgreSQL-backed E2E-тест coordinator/exchange для stale-result quarantine и нового lease.
3. Исправлен scheduler recovery bypass: lease-aware repository всегда использует транзакционный `recover_stale()`.
4. Исправлен Colab exchange worker: malformed claim после перемещения в `processing` гарантированно уходит в quarantine.
5. Исправлен production exchange submission через canonical PostgreSQL state и lease ownership.
6. Исправлен production result application через PostgreSQL lease ownership вместо эфемерного `InMemoryRepository`.
7. Исправлен PostgreSQL bootstrap и идемпотентное создание stage jobs.
8. Oracle scheduler daemon вынесен в отдельный production entrypoint.
9. Oracle daemon усилен повтором после временной ошибки цикла.
10. Добавлен dry-run документационный путь полного exchange-контракта.
11. Добавлен regression test на очистку `processing` после ошибки публикации результата.

## CI

Последний `main` на коммите `a25b33a6ba7f5db293560ff8bc42ecec28e01a46` зелёный:

- `Validate #337` — **success**.
- `CI Smoke #238` — **success**.
- Оба workflow завершились 2026-09-15 после изменения `test: cover exchange publish failure cleanup`.
- Автоматический retry не потребовался.

## Критический архитектурный блокер

Контракт pipeline объявляет 9 стадий:

`ingest → normalize → asr → diarization → embeddings → text_analysis → topics → linking → graph`.

При этом текущий `scripts/colab_inference.py` реально реализует GPU-процессоры только для `asr` и `diarization`; `embeddings` обрабатывается отдельной веткой `colab_exchange_worker.py`. Стадии `ingest`, `normalize`, `text_analysis`, `topics`, `linking`, `graph` пока не имеют полного production processor/worker пути.

Дополнительно `input_artifact_id` сейчас служит scheduler dependency, но downstream worker не разрешает этот artifact ID в физический входной файл: resolver в GPU inference работает с `input_path`/исходной записью. Поэтому даже после добавления недостающих processors необходимо завершить реальный artifact transport, иначе pipeline будет формально последовательным, но фактически повторно читать исходное аудио.

## Следующая инженерная очередь

1. Ввести явную capability/routing модель worker'ов: Oracle-local stages и Colab GPU stages не должны конкурировать за одну и ту же очередь вслепую.
2. Реализовать processors для `ingest`/`normalize` и определить canonical artifact storage/manifest для их результатов.
3. Переделать artifact resolution так, чтобы `input_artifact_id` однозначно разрешался в физический artifact, а не заменялся исходным `input_path`.
4. Реализовать или явно подключить workers для `text_analysis`, `topics`, `linking`, `graph`.
5. Добавить capability/routing integration tests, которые доказывают, что неподдерживаемая стадия не отправляется неподходящему worker.
6. После этого повторить dry-run полного 9-stage пути.
7. Затем выполнить реальный Oracle ARM smoke без production audio.
8. Затем реальный Colab GPU test с тестовым аудио и lease ownership.
9. Только после успешного полного E2E перейти к ограниченному production smoke.

## Ограничение

Бесплатный Google Colab не предоставляет гарантированный headless/public API. Поэтому Colab остаётся best-effort GPU worker через exchange/runner механизм, а Oracle должен оставаться устойчивым оркестратором и источником истины состояния.
