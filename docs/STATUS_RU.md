# Статус проекта Transcribe

Дата проверки: 2026-09-16

## Текущее состояние

Ядро распределённого execution pipeline доведено до устойчивого PostgreSQL/lease/exchange уровня. Полный 9-стадийный dry-run проходит в CI, включая Oracle и Colab exchange worker entrypoints, capability routing и канонические artifact dependencies.

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

Последнее подтверждённое состояние текущего `main`:

- `main` = `7f7326493d23a112ef66fc61a612288cb8dfce7b`.
- `Validate #538` — **success**, run `35136116518`, job `104928796127`.
- `CI Smoke #443` — **success**, run `35136116746`, job `104928797160`.
- Validate на предыдущем runtime SHA выполнил compile, notebook JSON/structure validation, schema validation, lint, полный тестовый набор, entrypoint checks и repository structure checks.
- Validate подтвердил **222 passed**.
- Smoke подтвердил Oracle-local worker integration: **5 passed**.
- Retry workflow checks skipped, поскольку основной CI не завершался ошибкой.
- Workflow artifacts не требуются для текущей валидации; Validate/Smoke не публикуют отдельный artifact bundle.

Документационное обновление этого status-файла находится в текущем `main`; после него требуется отдельное прохождение CI, поскольку этот commit был создан уже после указанных выше runtime checks.

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
