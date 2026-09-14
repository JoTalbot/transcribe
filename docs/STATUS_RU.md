# Статус проекта Transcribe

Дата проверки: 2026-09-14

## Текущее состояние

Проект находится на этапе доводки безопасного распределённого исполнения перед подключением реальных Oracle/Colab worker-процессов.

### Проверено и усилено

- PostgreSQL используется как каноническое состояние execution jobs.
- Захват задания защищён транзакционным lease-механизмом.
- Два конкурентных worker-процесса не должны получить одно и то же задание.
- `worker + lease_id` обязательны для heartbeat, completion и failure.
- Просроченный lease может быть переотдан другому worker.
- Старый worker не может завершить уже переотданное задание.
- Просроченный lease переводится в `retry`, а при достижении лимита попыток в `failed`.
- Integration tests покрывают heartbeat и предельное число попыток.
- PostgreSQL integration test покрывает полный обмен: dispatch → lease → reclaim → stale-result quarantine → принятие результата нового worker.
- Scheduler для DB-backed repository не может случайно перейти на небезопасный legacy recovery path из-за переданного тестового `now`.
- Colab worker не оставляет malformed claim в `processing`: такой request отправляется в quarantine.
- Worker tests соответствуют обязательному `worker + lease_id` протоколу.

## Последние исправления

1. Убрана зависимость integration tests от фиксированных задержек истечения lease. Ожидание reclaim/recovery выполняется через bounded polling с монотонным таймером. Временные PostgreSQL-соединения закрываются после проверок.
2. Добавлен PostgreSQL-backed E2E-тест coordinator/exchange: результат старого worker после reclaim не меняет состояние задания и перемещается в quarantine, а результат нового worker с актуальным `lease_id` успешно завершает задание.
3. Исправлен scheduler recovery bypass: lease-aware repository всегда использует транзакционный `recover_stale()`.
4. Исправлен Colab exchange worker: malformed claim после перемещения в `processing` гарантированно уходит в quarantine.
5. Исправлен production exchange submission: `scripts/submit_exchange_jobs.py` больше не создаёт exchange jobs напрямую из локального `JobStore`. Теперь он требует PostgreSQL, сверяет manifest paths с каноническими записями БД и выполняет dispatch через `Scheduler`/`ExchangeCoordinator` с lease ownership.

## CI

Для последних изменений GitHub Actions должен завершить новый push-triggered запуск `Validate`. До получения фактического успешного результата нельзя объявлять проект CI-green.

## Следующий production gate

1. Получить успешный полный CI после текущих исправлений.
2. Если CI найдёт ошибку, исправить её в репозитории и повторить проверку.
3. Проверить реальные production entrypoints Oracle/Colab и убедиться, что они используют lease-aware coordinator/repository, а не legacy `JobStore` dispatch.
4. После подтверждения безопасного пути выполнить dry-run без пользовательского production-аудио.
5. Затем выполнить ограниченный production smoke test.

## Ограничение

Бесплатный Google Colab не предоставляет гарантированный headless/public API. Поэтому Colab остаётся best-effort GPU worker через предусмотренный exchange/runner механизм, а Oracle должен оставаться устойчивым оркестратором и источником истины состояния.
