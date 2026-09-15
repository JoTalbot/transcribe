# Статус проекта Transcribe

Дата проверки: 2026-09-15

## Текущее состояние

Ядро распределённого execution pipeline доведено до устойчивого PostgreSQL/lease/exchange уровня. **Полный 9-стадийный dry-run проходит в CI**, включая Oracle и Colab exchange worker entrypoints, capability routing и канонические artifact dependencies.

Production E2E с реальными Whisper-large-v3, pyannote и ECAPA на Google Colab GPU **ещё не выполнен**, поэтому production-ready для полного пути пока не объявляется. Сначала тесты, потом распределённый хаос.

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
- Production bootstrap очереди создаёт recordings и stable stage jobs непосредственно в PostgreSQL.
- `scripts/submit_exchange_jobs.py` работает через PostgreSQL + `Scheduler`/`ExchangeCoordinator`.
- `scripts/apply_exchange_results.py` применяет результаты через PostgreSQL lease ownership.
- `scripts/oracle_worker.py` использует свежий PostgreSQL connection на цикл, применяет результаты, reclaim просроченных lease и dispatch через `Scheduler`/`ExchangeCoordinator`.
- Oracle daemon переживает временный сбой одного цикла и продолжает работу.
- Colab exchange worker очищает `processing` marker даже при неудаче публикации результата.
- Добавлен dry-run контракт Oracle → exchange без GPU и production audio.
- Capability routing разделяет `ingest`, `normalize`, `text_analysis`, `topics`, `linking`, `graph` на Oracle-local и `asr`, `diarization`, `embeddings` на Colab GPU.
- Oracle worker имеет локальные processors для `ingest`, `normalize`, `text_analysis`, `topics`, `linking`, `graph`.
- Colab inference использует artifact-driven входы для ASR и diarization.
- Colab exchange worker содержит отдельную ECAPA embedding ветку и публикует canonical `embeddings` artifact manifest.
- Cross-worker regression test проходит через реальные `process_one()` entrypoints обоих worker'ов и проверяет весь 9-stage маршрут и exact dependency artifact IDs.
- Успешно применённые exchange results удаляются после commit результата; stale/foreign/malformed results остаются в quarantine.
- Colab transport сохраняет `worker + lease_id` от execution job до file-exchange request, чтобы результат нельзя было принять за другой lease.
- README синхронизирован с Oracle daemon entrypoint.

## Последние исправления

1. Убрана зависимость integration tests от фиксированных задержек истечения lease.
2. Добавлен PostgreSQL-backed E2E-тест stale-result quarantine и нового lease.
3. Исправлен scheduler recovery bypass для lease-aware repository.
4. Исправлен Colab exchange worker: malformed claim после перемещения в `processing` гарантированно уходит в quarantine.
5. Исправлен production exchange submission через canonical PostgreSQL state и lease ownership.
6. Исправлен production result application через PostgreSQL lease ownership.
7. Исправлен PostgreSQL bootstrap и идемпотентное создание stage jobs.
8. Oracle scheduler daemon вынесен в отдельный production entrypoint и усилен повтором после временной ошибки цикла.
9. Добавлен dry-run контракт полного 9-stage exchange пути.
10. Добавлен regression test на очистку `processing` после ошибки публикации результата.
11. Исправлена обработка результата exchange: успешно применённый result больше не повторно попадает в stale/quarantine на следующем цикле.
12. Добавлены capability-aware routing и cross-worker 9-stage regression проверки.
13. Исправлен cross-worker dry-run test: production `dry_run_processor` сохранён с его контрактом `dry-run:<job_id>`, а тест использует отдельный canonical processor для проверки artifact routing.
14. Lease identity сохранён через Colab backend и file exchange; добавлены regression tests на worker/lease propagation.
15. Усилен recovery контроль `processing` marker: malformed/inconsistent marker консервативно блокирует dispatch, валидный orphaned marker после lease recovery уходит в quarantine.

## CI

Последний проверенный `main` — `7cdcd0cbd3393585d64452e201da3cd972ab5f19`.

- `Validate #411` — **success**.
- `CI Smoke #312` — **success**.
- `Validate` успешно прошёл compile, notebook JSON/structure, conversation schema, lint, **PostgreSQL integration tests**, script entrypoints и repository validation.
- `CI Smoke` успешно выполнил Oracle-local worker smoke.
- Предыдущий `Validate #410` на commit с первым вариантом Colab lease fix падал на lint; ошибка исправлена отдельным commit `7cdcd0c`, после чего полный `Validate #411` стал зелёным.

## Канонический 9-stage pipeline

`ingest → normalize → asr → diarization → embeddings → text_analysis → topics → linking → graph`

### Routing

| Stage | Worker |
|---|---|
| `ingest` | Oracle-local |
| `normalize` | Oracle-local |
| `asr` | Colab GPU |
| `diarization` | Colab GPU |
| `embeddings` | Colab GPU |
| `text_analysis` | Oracle-local |
| `topics` | Oracle-local |
| `linking` | Oracle-local |
| `graph` | Oracle-local |

Dry-run доказывает логический маршрут и artifact dependencies. Это **не** доказывает производительность или корректность реальных GPU-моделей на аудио.

## Оставшийся production блок

Главный незакрытый блок теперь не в очереди, lease или routing, а в **реальном межсредовом artifact transport + GPU E2E**:

1. Зафиксировать production exchange layout для canonical artifacts между Oracle/Drive и Colab.
2. Убедиться, что manifests и физические artifact files доступны Colab resolver'у после Oracle `normalize` и обратно после GPU stages.
3. Выполнить реальный Colab GPU test на коротком тестовом аудио с `Whisper large-v3`, `pyannote/speaker-diarization-3.1` и SpeechBrain ECAPA.
4. Проверить все 9 stages end-to-end с PostgreSQL lease ownership, включая reclaim/retry при прерывании worker.
5. Зафиксировать время выполнения, VRAM/RAM и размеры artifacts для GPU stages.
6. Проверить повторный запуск и отсутствие duplicate/corrupt artifacts.
7. После успешного E2E выполнить ограниченный production smoke.

## Ограничение

Бесплатный Google Colab не предоставляет гарантированный headless/public API. Поэтому Colab остаётся best-effort GPU worker через exchange/runner механизм, а Oracle должен оставаться устойчивым оркестратором и источником истины состояния.
