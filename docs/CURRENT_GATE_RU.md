# Текущий production gate

Дата проверки: 2026-09-16

## Репозиторий

- Ветка: `main`
- Текущий commit: `e3603ac60106295312b5176c80a5a8828a978e64`
- Изменение: `fix: install Colab dependencies before importing torch`

## Подтверждено репозиторием

- Repository validation проходит на текущем `main`.
- `Validate #546` для текущего commit завершился успешно.
- Проверяются Python compilation, notebook JSON/structure, conversation schema, lint, полный pytest, entrypoints и структура репозитория.
- Colab notebook устанавливает GPU-зависимости до импорта `torch`.
- 9-stage pipeline, capability routing, artifact verification, immutable publication, lease/reclaim и stale-result quarantine реализованы и покрыты repository-side проверками.

## Что ещё не является доказанным

CI и dry-run не подтверждают физическую работу GPU-моделей в Google Colab.

Для production acceptance требуется один реальный проход:

`Oracle → Google Drive exchange → Colab CUDA → Whisper large-v3 → pyannote speaker-diarization-3.1 → SpeechBrain ECAPA → Google Drive exchange → Oracle/PostgreSQL`

Дополнительно требуется:

1. Зафиксировать wall-clock timings.
2. Зафиксировать model load time.
3. Зафиксировать RAM/VRAM.
4. Зафиксировать размеры и SHA-256 артефактов.
5. Повторить запуск и подтвердить отсутствие duplicate/corrupt outputs.
6. Прервать Colab worker, дождаться lease expiry/reclaim.
7. Подтвердить quarantine старого результата и успешное завершение под новым lease.
8. Сохранить evidence snapshot через `scripts/colab_gpu_evidence.py`.

До получения этой физической evidence production gate остаётся открытым.
