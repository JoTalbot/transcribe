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
- Oracle local worker также защищает существующий `processing/<job>.json` от перезаписи; добавлен regression coverage.
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
- Stale request со старым worker/lease после reclaim также уходит в quarantine и не блокирует новый dispatch.
- Проверен сценарий foreign processing lease для уже running job.
- Notebook CI проверяет наличие canonical Colab exchange worker, Drive paths и production model families.
- Drive sync сверяет обработанное состояние по reconciliation между Drive records и legacy local paths.
- Изменённые Drive-файлы повторно скачиваются по `modifiedTime`, при этом сохраняется `size`.
- Добавлены regression tests для Drive processed-state reconciliation, повторной загрузки изменённого файла и пропуска неизменённого файла.
- Добавлен auditable Colab GPU evidence collector, который фиксирует GPU/CUDA/package metadata и проверяет artifact manifests, размер и SHA-256 без вывода секретов.
- Для физического GPU E2E добавлен отдельный evidence template с timing, RAM/VRAM, model-load, artifact, repeat и interruption/reclaim полями.
- File exchange отвергает `job_id` с разделителями путей и NUL-байтом, чтобы exchange filename не мог выйти за пределы `requests/` или `results/`; защита покрыта regression test.
- Atomic JSON writer больше не использует общий фиксированный `.tmp` путь: конкурентные writers получают независимые временные файлы, содержимое flush/fsync-ится перед replace; добавлен regression test конкурентной записи.
- Artifact audit теперь отдельно выявляет `invalid_manifest`, duplicate artifact IDs, missing/orphan payloads, checksum/size mismatches и **любые declared paths вне artifact root, включая относительные `../...` пути**.
- Artifact audit работает read-only и возвращает ненулевой exit code при обнаружении нарушений.
- Canonical artifact publishers (`ingest`, `normalize`, ASR/diarization, local intelligence, speaker clustering, Colab embeddings) используют immutable publication semantics вместо перезаписи уже существующего payload.

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
19. Синхронизирован статусный документ с фактическим runtime baseline и последними подтверждёнными CI runs.
20. Добавлена защита Colab claim от перезаписи уже существующего `processing` marker.
21. Добавлен regression test на отказ от перезаписи существующего Colab processing claim.
22. Повторно синхронизированы runtime baseline и CI evidence после документационных коммитов.
23. Перепроверен и повторно запущен отменённый `CI Smoke #363`; второй attempt завершился успешно.
24. Добавлен отдельный auditable evidence template для физического Colab GPU E2E.
25. Добавлен Colab GPU evidence collector с проверкой artifact manifests и GPU metadata.
26. Исправлена совместимость evidence collector с публичным `ArtifactResolver` API и добавлены regression tests для verified/tampered artifacts.
27. Документирован запуск evidence collector в Colab exchange contract.
28. Подтверждены функциональные `Validate #471` и `CI Smoke #375` на runtime baseline после синхронизации evidence tooling.
29. Подтверждены более новые функциональные `Validate #472` и `CI Smoke #376`; статус теперь не привязывает себя к SHA документационного коммита.
30. Усилена граница file exchange: `job_id` больше не может содержать `/`, `\\` или NUL и использоваться для выхода из exchange subdirectory; добавлен regression coverage.
31. Устранена конкуренция за общий `.tmp` файл при записи exchange JSON: каждый writer теперь использует уникальный временный файл и fsync перед replace.
32. Добавлен regression test на конкурентные writers одного exchange record.
33. Добавлена regression-проверка stale request после lease reclaim: старый request уходит в quarantine, после чего job может быть повторно dispatch-нута с новым lease.
34. Исправлена публикация Oracle-local artifacts: конкурентная попытка больше не может заменить уже существующий payload через `temporary.replace()`.
35. Добавлены immutable publication checks для speaker clustering и Colab ECAPA embedding artifacts.
36. Добавлена отдельная read-only проверка artifact store через `scripts/audit_artifacts.py` и regression coverage для duplicate/missing/orphan/checksum/path-boundary случаев.
37. Исправлена проверка artifact audit для относительных путей вне root: `../outside/...` теперь корректно помечается как `path_outside_root`.

## CI

Последнее подтверждённое состояние после artifact-audit hardening:

- `Validate` для commit `8058c5b99237da1663ca7bf4b6087efd7e09d6d3` — **success**; run `35120817504`, job `104877835669`. Прошли compile, notebook JSON/structure, schema, lint, все тесты, entrypoints и repository structure.
- `CI Smoke` для того же commit — **success**; run `35120817607`, job/check `104877837299`. Прошли repository validation и `Exercise Oracle-local worker`.
- Два дополнительных автоматических `retry` check-run на этом SHA имеют статус `skipped`, что соответствует ожидаемому поведению и не является ошибкой.
- Последний подтверждённый runtime baseline `Validate #472` / `CI Smoke #376` таким образом заменён более новым зелёным runtime baseline на commit `8058c5b9`.
- CI и dry-run не выполняют реальный GPU inference в Google Colab и поэтому не могут закрыть physical E2E gate.

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
10. Evidence collector сохраняет машиночитаемое подтверждение GPU/CUDA/package/artifact state.
11. Только после этого можно считать физический production E2E подтверждённым.

Для этого уже существуют `docs/COLAB_GPU_E2E_CHECKLIST_RU.md` и `docs/COLAB_GPU_E2E_EVIDENCE_TEMPLATE_RU.md`.

## Ограничение

Бесплатный Google Colab не предоставляет гарантированный headless/public API. Поэтому Colab остаётся best-effort GPU worker через exchange/runner механизм, а Oracle должен оставаться устойчивым оркестратором и источником истины состояния.
