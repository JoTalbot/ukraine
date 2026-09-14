# Ukraine — Production Readiness Report

**Дата:** 2026-09-14  
**Репозиторий:** `JoTalbot/ukraine`  
**Аудит:** production readiness / fail-closed release control

## Итог

**Control plane: GREEN по архитектуре и контрактам. Полный data product: NOT YET CERTIFIED.**

Production намеренно остаётся **RED / fail-closed**: discovery bootstrap не завершён, реального production artifact/evaluation evidence недостаточно, а authoritative production authorization не оформлена для конкретного проверенного release.

## Шаг 1 — Повторная проверка production readiness

Проверены readiness gate, hardening, artifact chain, promotion authorization, discovery state и release-control workflow. Readiness дополнительно связывает promotion gate с реальным verifier авторизации, включая проверку существования и SHA-256 production artifact и evaluation evidence.

Это закрывает semantic gap: одного корректного JSON authorization недостаточно, если указанные реальные файлы не существуют или их содержимое изменилось.

## Шаг 2 — Security path safety

`verify_promotion_authorization.py` принимает только относительные пути внутри `artifacts/`, запрещает абсолютные пути и `..`, после `resolve()` проверяет принадлежность корню репозитория. Это fail-closed поведение.

## Шаг 3 — Discovery publication truthfulness

В `.github/workflows/discovered-open-data-huggingface.yml` сохранение progress отделено от финального failure. Если batch содержит failed resources, progress сначала фиксируется, затем job получает `failure`, после чего `always()` publication signal становится RED.

Проверка run `34848512473` подтвердила исправление: batch обработан, обнаружено 53 failed resources, `Persist bootstrap progress` завершился успешно, состояние было отправлено в `main`, после чего job намеренно завершился с `exit 1`. Это корректный RED результат, а не потеря состояния из-за ошибки CI.

## Шаг 4 — Исправление starvation в scheduler

Найдена отдельная liveness-ошибка: при наличии любого `failed_batches` scheduler всегда выбирал минимальный failed batch и мог бесконечно не доходить до ещё не проверенных batch.

Исправлено в commit `d726ad9251ed119bf9dd616a04e49fe84a89a233`: теперь при bootstrap сначала выбирается первый **неуспешный и ещё не падавший** batch; retry failed batches начинается только после исчерпания всех непроверенных batch. Ручной `batch_index` сохраняет приоритет, а `bootstrap_complete` по-прежнему останавливает bootstrap.

Добавлен regression test в commit `22f30ccc071754477502c5518bdb5c770a8ae926`, который фиксирует порядок `unattempted -> retry` и предотвращает возврат starvation.

## Шаг 5 — Discovery state

Текущее состояние `main` остаётся честно неполным:

- `batch_count=360`;
- `failed_batches=0..20`;
- `successful_batches=[]`;
- `completed_batches=0`;
- `next_batch=21`;
- `bootstrap_complete=false`.

Ни один failed batch искусственно успешным не объявлялся. Последняя зафиксированная запись состояния имеет timestamp `2026-09-14T13:49:52.130227+00:00`.

## Шаг 6 — Причина текущих data failures

Runtime evidence показывает два класса внешних проблем источников:

- `data.gov.ua`: HTTP `429 Too Many Requests` на части ресурсов;
- `opendata.gov.ua`: `ConnectTimeout` при скачивании части ресурсов.

Это реальные source-side availability/rate-limit failures. Pipeline корректно учитывает их как failed resources, сохраняет progress и оставляет publication RED. Их нельзя превращать в успешный batch только ради зелёного CI, потому что тогда контрольная система начнёт врать.

## Шаг 7 — Усиление retry/backoff

В commit `9027ad2b385715c55bd8ead414756fae53100da7` усилена загрузка discovered resources:

- HTTP `429` теперь явно считается retryable;
- все `5xx` остаются retryable;
- используется серверный `Retry-After`, если он присутствует;
- задержка ограничена `DATA_GOV_MAX_RETRY_WAIT` (по умолчанию 60 секунд), чтобы внешний источник не мог заставить runner ждать бесконечно;
- при отсутствии корректного `Retry-After` сохраняется экспоненциальный backoff;
- после исчерпания попыток ресурс остаётся failed, поэтому readiness/truthfulness gate не ослабляется.

Добавлены regression tests в commit `2716cc979c2bfcdb9564c4b90986649252d242cf` для bounded `Retry-After` и fallback exponential backoff.

## Шаг 8 — CI verification

После commit `2716cc979c2bfcdb9564c4b90986649252d242cf` GitHub Actions создал новые runs `Ukraine data CI #527` и `Security scan #188`. На момент фиксации отчёта они находятся в `queued`, поэтому зелёный результат пока **не заявляется**. Production Release Gate после документационного коммита остаётся RED, что соответствует отсутствию authoritative production authorization.

## Шаг 9 — Остаточные слабые места

### P0

1. Завершить discovery bootstrap: `successful_batches == batch_count`, `failed_batches == []`, `bootstrap_complete=true`.
2. Прогнать и подтвердить новый retry/backoff код в CI и runtime discovery.
3. Получить реальные production artifact и evaluation evidence.
4. Оформлять authorization только для конкретного проверенного release и фактически существующих файлов.

### P1

5. Защитить authorization отдельной approval boundary: protected environment/branch или криптографическая подпись.
6. Добавить независимый signed provenance/attestation.
7. Добавить deployment-side atomic rollback и фактический recovery test.
8. Запустить end-to-end regression CI после изменений readiness verifier-binding и зафиксировать результат в отчёте.

### P2

9. Расширить freshness/retry/recovery observability.
10. Добавить периодическую end-to-end production certification.

## Сертификационная матрица

| Контур | Статус |
|---|---|
| Production architecture | **GREEN** |
| Hardening contracts | **GREEN / УКРЕПЛЕНЫ** |
| Promotion path safety | **GREEN** |
| Readiness → real artifact binding | **GREEN / УСИЛЕНО** |
| Discovery publication truthfulness | **GREEN / УКРЕПЛЕНО** |
| Discovery progress persistence | **GREEN / ПРОВЕРЕНО RUNTIME** |
| Discovery scheduler liveness | **GREEN / ИСПРАВЛЕНО + TEST** |
| Rate-limit/timeout retry policy | **GREEN / УСИЛЕНО + TEST** |
| Cryptographic artifact chain | **УКРЕПЛЕНА, НЕ SIGNED PROVENANCE** |
| Authoritative promotion authorization | **RED / ОТСУТСТВУЕТ** |
| Discovery bootstrap | **RED / НЕ ЗАВЕРШЁН** |
| Real producer evidence | **RED / НЕДОСТАТОЧНО** |
| Deployment rollback evidence | **RED / НЕДОСТАТОЧНО** |
| Full production certification | **RED / NOT YET CERTIFIED** |

## Изменения этого батча

1. `9027ad2b385715c55bd8ead414756fae53100da7` — добавлен bounded `Retry-After`/exponential backoff для discovery downloads.
2. `2716cc979c2bfcdb9564c4b90986649252d242cf` — добавлены regression tests retry/backoff.
3. Текущее состояние discovery повторно проверено: `next_batch=21`, failed `0..20`, успешных `0`, bootstrap incomplete.

## Решение

**PRODUCTION HARDENING IN PROGRESS. CONTROL-PLANE ARCHITECTURE GREEN. FULL DATA PRODUCT NOT YET CERTIFIED.**

Следующий обязательный рубеж: дождаться CI verification нового retry/backoff кода и runtime-проверить продвижение scheduler к batch `21+`. После завершения discovery нужны реальные producer/evaluation/release evidence, затем защищённое approval и deployment/rollback verification. До этого production должен оставаться заблокированным.