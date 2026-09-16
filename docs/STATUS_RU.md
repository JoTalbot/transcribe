# Статус проекта Transcribe

Дата проверки: 2026-09-16

## Текущее состояние

Ядро распределённого execution pipeline доведено до устойчивого PostgreSQL/lease/exchange уровня. **Полный 9-стадийный dry-run проходит в CI**, включая Oracle и Colab exchange worker entrypoints, capability routing и канонические artifact dependencies.

Production E2E с реальными Whisper-large-v3, pyannote и ECAPA на Google Colab GPU **ещё не выполнен**, поэтому production-ready для полного пути пока не объявляется. Кодовая часть закрыта значительно дальше, чем физическая инфраструктура, что, к сожалению, является нормальным свойством распределённых систем.

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
- Colab worker не должен перезаписывать существующий `processing/<job>.json`; этот конфликт покрыт regression test.
- Production bootstrap очереди создаёт recordings и stable stage jobs непосредственно в PostgreSQL.
- `scripts/submit_exchange_jobs.py` работает через PostgreSQL + `Scheduler`/`ExchangeCoordinator`.
- `scripts/apply_exchange_results.py` применяет результаты через PostgreSQL lease ownership.
- `scripts/oracle_worker.py` использует свежий PostgreSQL connection на цикл, применяет результаты, reclaim просроченных lease и dispatch через `Scheduler`/`ExchangeCoordinator`.
- Oracle daemon переживает временный сбой одного цикла и продолжает работу.
- Colab exchange worker очищает `processing` marker после обработки, включая ошибочные пути; ошибка публикации результата не оставляет marker.
- Добавлен dry-run контракт Oracle → exchange без GPU и production audio.
- Capability routing разделяет `ingest`, `normalize`, `text_analysis`, `topics`, `linking`, `graph` на Oracle-local и `asr`, `diarization`, `embeddings` на Colab GPU.
- Oracle worker имеет локальные processors для `ingest`, `normalize`, `text_analysis`, `topics`, `linking`, `graph`.
- Colab inference использует artifact-driven входы для ASR и diarization.
- Colab exchange worker содержит отдельную ECAPA embedding ветку и публикует canonical `embeddings` artifact manifest.
- Cross-worker regression test проходит через реальные `process_one()` entrypoints обоих worker'ов и проверяет весь 9-stage маршрут и exact dependency artifact IDs.
- Успешно применённые exchange results удаляются после commit результата; stale/foreign/malformed results остаются в quarantine.
- Colab transport сохраняет `worker + lease_id` от execution job до file-exchange request, чтобы результат нельзя было принять за другой lease.
- Artifact verification проверяет существование, размер, SHA-256, exchange-root confinement, recording binding и stage binding.
- Processing marker со старым worker/lease после reclaim больше не блокирует повторный dispatch и уходит в quarantine.
- Проверен сценарий foreign processing lease для уже running job.
- Notebook CI проверяет наличие canonical Colab exchange worker, Drive paths и production model families.
- Drive sync сверяет обработанное состояние по reconciliation между Drive records и legacy local paths.
- Изменённые Drive-файлы повторно скачиваются по `modifiedTime`, при этом сохраняется `size`.
- Добавлены regression tests для Drive processed-state reconciliation, повторной загрузки изменённого файла и пропуска неизменённого файла.

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
13. Lease identity сохранён через Colab backend и file exchange; добавлены regression tests на worker/lease propagation.
14. Усилен recovery контроль `processing` marker: malformed/inconsistent marker консервативно блокирует dispatch.
15. Добавлена защита от foreign processing marker после смены lease.
16. Добавлены проверки cross-recording и cross-stage artifact binding.
17. Восстановлен полный Colab exchange worker после неполной промежуточной версии и исправлен импорт `src` при прямом запуске script entrypoint.
18. Синхронизирована документация Colab exchange с фактическим production worker и canonical `requests/processing/results/artifacts` layout.
19. Синхронизирован статусный документ с фактическим `main` и последними CI runs.
20. Добавлена защита Colab claim от перезаписи уже существующего `processing` marker.
21. Добавлен regression test на отказ от перезаписи существующего Colab processing claim.
22. Повторно синхронизированы main SHA и CI run numbers после документационного коммита.
23. Перепроверен и повторно запущен отменённый `CI Smoke #363`; второй attempt завершился успешно.
24. Добавлен отдельный auditable evidence template для физического Colab GPU E2E.
25. Повторно синхронизирован статусный документ после подтверждения успешного второго attempt `CI Smoke #363`.

## CI

Фактически подтверждённые GitHub Actions для функционального состояния:

- `Validate #459` — **success**; прошли compile, notebook JSON/structure, schema, lint, tests, script entrypoints и repository structure.
- `CI Smoke #363`, attempt 2 — **success**; прошли repository validation и Oracle-local worker smoke.

Первоначальный attempt `CI Smoke #363` был отменён concurrency-механизмом, после чего был выполнен повторный запуск. Успешный второй attempt является фактическим результатом проверки.

Текущий `main` после документационной синхронизации: `a40392f3775367bbed5090c7e035dd8156761d67`. Новый commit документации должен пройти обычную CI-проверку. CI не выполняет реальный GPU inference в Google Colab и поэтому не может закрыть physical E2E gate.

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

Главный незакрытый блок теперь не в очереди, lease, routing или artifact verification, а в **реальном межсредовом artifact transport + GPU E2E**:

1. Oracle создаёт canonical `source_audio` и `normalize:audio` artifacts.
2. Эти artifacts физически доступны Colab через общий Drive exchange.
3. Colab реально запускает Whisper `large-v3`.
4. Затем реально запускаются pyannote `speaker-diarization-3.1` и SpeechBrain ECAPA.
5. GPU artifacts возвращаются в exchange и принимаются Oracle/PostgreSQL.
6. Все 9 stages доходят до `completed`.
7. Выполняется повторный запуск и проверяется отсутствие duplicate/corrupt artifacts.
8. Выполняется interruption/reclaim/retry smoke со старым и новым lease.
9. Фиксируются wall-clock timings, RAM/VRAM и размеры artifacts.
10. Только после этого можно считать физический production E2E подтверждённым.

Для этого уже существует `docs/COLAB_GPU_E2E_CHECKLIST_RU.md` и `docs/COLAB_GPU_E2E_EVIDENCE_TEMPLATE_RU.md`.

## Ограничение

Бесплатный Google Colab не предоставляет гарантированный headless/public API. Поэтому Colab остаётся best-effort GPU worker через exchange/runner механизм, а Oracle должен оставаться устойчивым оркестратором и источником истины состояния.
