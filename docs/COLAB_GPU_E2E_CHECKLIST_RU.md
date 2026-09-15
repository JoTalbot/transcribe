# Transcribe: чек-лист реального Colab GPU E2E

Дата: 2026-09-15

## Цель

Проверить не dry-run, а реальный маршрут:

`Oracle PostgreSQL → exchange/artifacts → Colab GPU → exchange/results → Oracle PostgreSQL → все 9 стадий`

GPU-стадии выполняются на Colab: `asr → diarization → embeddings`. Oracle выполняет `ingest → normalize → text_analysis → topics → linking → graph`.

## Перед запуском

1. Oracle имеет рабочий PostgreSQL и запущен `scripts/oracle_worker.py`.
2. Exchange root доступен обоим worker'ам через общий Drive/файловый transport.
3. В Colab включён GPU и `torch.cuda.is_available()` возвращает `True`.
4. В Colab Secrets существует `HUGGINGFACE_TOKEN` с правом чтения.
5. Приняты условия моделей `pyannote/speaker-diarization-3.1` и требуемых зависимостей Hugging Face.
6. В exchange есть небольшой тестовый WAV без чувствительных данных.

## Запуск Colab worker

В Colab выполнить notebook setup, затем:

```bash
python scripts/colab_exchange_worker.py \
  --root /content/drive/MyDrive/transcribe/exchange \
  --input /content/drive/MyDrive/transcribe/input \
  --output /content/drive/MyDrive/transcribe/exchange/artifacts
```

Для диагностики одного задания использовать `--once`.

## Критерии успешного E2E

- `ingest` создаёт и публикует canonical `source_audio` artifact.
- `normalize` создаёт checksum-verified PCM16 mono 16 kHz WAV.
- `asr` получает именно `*:normalize:audio`, запускает Whisper `large-v3` и публикует `*:asr:json`.
- `diarization` получает именно `*:asr:json`, использует pyannote и публикует `*:diarization:json`.
- `embeddings` получает именно `*:diarization:json`, использует SpeechBrain ECAPA и публикует `*:embeddings:json`.
- `text_analysis`, `topics`, `linking`, `graph` получают ожидаемые canonical artifacts и завершаются на Oracle.
- Все 9 execution jobs имеют `completed`.
- Ни один результат не попадает в `results/quarantine`.
- После применения результата файл результата удаляется из `results/`.
- Lease ownership сохраняется на каждом GPU job: старый worker не может применить результат после reclaim.
- В PostgreSQL сохраняются финальные artifact IDs и recording status.

## Что измерить

Зафиксировать:

- тип и объём GPU VRAM;
- время загрузки Whisper/pyannote/ECAPA;
- время ASR;
- время diarization;
- время embeddings;
- общий E2E runtime;
- максимальное потребление RAM/VRAM;
- размер входного аудио и всех ключевых artifacts.

## Failure/recovery smoke

После успешного базового E2E отдельно проверить:

1. остановку Colab worker во время GPU job;
2. истечение lease;
3. reclaim задания Oracle scheduler'ом;
4. появление результата старого lease;
5. его quarantine;
6. повторное выполнение задания новым lease;
7. успешное завершение pipeline.

## Статус готовности

До прохождения этого чек-листа production Colab/Oracle E2E считается **непроверенным**. Зеленый GitHub CI и полный dry-run доказывают кодовый контракт, но не заменяют физический запуск GPU-инференса. Это неприятная, но полезная граница между программой и реальностью.
