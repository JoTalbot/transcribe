# Статус проекта Transcribe

Дата актуализации: 2026-09-17

## Текущее состояние

Ядро распределённого execution pipeline доведено до устойчивого PostgreSQL/lease/exchange уровня. Полный 9-стадийный dry-run проходит в CI, включая Oracle и Colab exchange worker entrypoints, capability routing и канонические artifact dependencies.

Последнее функциональное изменение усиливает захват Colab exchange job: `processing/<job>.json` создаётся эксклюзивно через `O_EXCL`, поэтому конкурентные workers не могут перезаписать существующий claim. После создания claim request удаляется; если удаление исходного request не удалось, claim сохраняется, чтобы не открыть повторный захват.

Production E2E с реальными Whisper large-v3, pyannote и SpeechBrain ECAPA на Google Colab GPU ещё не выполнен. Поэтому полный production-ready статус для физического GPU пути пока не объявляется.

## Подтверждено

- PostgreSQL является каноническим состоянием execution jobs.
- Захват задания защищён транзакционным lease-механизмом.
- `worker + lease_id` используются для heartbeat, completion и failure.
- Просроченный lease может быть переотдан другому worker.
- Старый worker не может завершить уже переотданное задание.
- Recovery переводит просроченные jobs в retry либо failed при достижении лимита попыток.
- PostgreSQL integration coverage включает dispatch → lease → reclaim → stale-result quarantine → принятие результата нового worker.
- Oracle daemon переживает временный сбой отдельного цикла.
- Oracle и Colab exchange workers защищены от перезаписи существующего `processing/<job>.json` marker.
- При уже существующем processing claim исходный request сохраняется и не переносится в quarantine.
- Colab claim теперь использует эксклюзивное создание файла (`O_CREAT | O_EXCL`) вместо check-then-create.
- После успешного создания processing claim исходный request удаляется; ошибка удаления не отменяет уже созданный claim.
- Malformed и stale/foreign processing markers после проверки отправляются в quarantine и не блокируют новый dispatch.
- Stale request после lease reclaim также отправляется в quarantine.
- Exchange сохраняет `worker + lease_id` от execution job до результата.
- `job_id` с `/`, `\\` или NUL отклоняется, поэтому exchange filename не может выйти за пределы целевой директории.
- ArtifactResolver проверяет artifact ID, duplicate IDs, размер, SHA-256, exchange-root confinement, recording binding и stage binding.
- Canonical artifact publishers используют immutable publication semantics.
- Конкурентные writers exchange JSON получают независимые временные файлы; содержимое flush/fsync-ится перед replace.
- Artifact audit (`scripts/audit_artifacts.py`) работает read-only и выявляет invalid manifests, duplicate IDs, missing/orphan payloads, checksum/size mismatches и declared paths вне artifact root, включая относительные `../...` пути.
- Colab GPU evidence collector фиксирует GPU/CUDA/package metadata и проверяет artifact manifests, размер и SHA-256 без вывода секретов.
- Evidence snapshots публикуются immutable-режимом.
- Cross-worker regression проходит через реальные `process_one()` entrypoints и проверяет весь 9-stage маршрут и exact dependency artifact IDs.
- Regression-тест подтверждает, что существующий processing claim не перезаписывается.
- Каноническая физическая E2E record-документация защищена regression-тестами и явно отделяет CI/dry-run от реального GPU evidence.
- Тестовый validator физического Colab GPU evidence проверяет CUDA/GPU/VRAM, package metadata, runtime metrics, все 9 stages и verified artifacts.

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

Dry-run подтверждает логический маршрут, lease/exchange semantics и artifact dependencies. Он не подтверждает производительность или корректность реальных GPU-моделей на физическом аудио.

## CI

На `main` был обнаружен и исправлен единственный lint-блокер в Colab claim implementation: Ruff `TRY203` отклонял бессмысленный `except OSError: raise`. Исправление опубликовано отдельным commit `c54068deb29a67a5adea4bf7fc5668c733963d49`.

Перед этим:

- `CI Smoke #522` для `35434aac605728962df6144ce45169b97a790e47` — **success**;
- `Validate #615` для `35434aac605728962df6144ce45169b97a790e47` — **failure** только на шаге `Lint Python` из-за Ruff `TRY203`; compile, notebook JSON/structure, conversation schema и установка зависимостей прошли успешно;
- предыдущие `Validate #611` и `CI Smoke #518` для функционального commit `9fd7b735cccac081e7028fb3c1bc1d53d10714b2` — **success**.
- Workflow permissions для validation ограничены `contents: read`.

После commit `c54068deb29a67a5adea4bf7fc5668c733963d49` CI должен быть перепроверен на новом head перед объявлением main зелёной.

CI и dry-run не выполняют реальный GPU inference в Google Colab и поэтому не закрывают physical E2E gate.

## Production validation remaining

Главный незакрытый блок находится не в очереди, lease, routing или artifact verification, а в реальном межсредовом artifact transport + GPU E2E:

1. Oracle создаёт canonical `source_audio` и `normalize:audio` artifacts.
2. Эти artifacts физически доступны Colab через общий Google Drive exchange.
3. Colab реально запускает Whisper `large-v3`.
4. Затем реально запускаются pyannote `speaker-diarization-3.1` и SpeechBrain ECAPA.
5. GPU artifacts возвращаются в exchange и принимаются Oracle/PostgreSQL.
6. Все 9 stages доходят до `completed`.
7. Выполняется повторный запуск и проверяется отсутствие duplicate/corrupt artifacts.
8. Выполняется interruption/reclaim/retry smoke со старым и новым lease.
9. Фиксируются wall-clock timings, RAM/VRAM, model-load time и размеры artifacts.
10. `scripts/colab_gpu_evidence.py` сохраняет машиночитаемое подтверждение GPU/CUDA/package/artifact state.
11. После успешного выполнения всех пунктов физический production E2E можно считать подтверждённым.
