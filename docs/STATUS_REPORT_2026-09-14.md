# Ukraine — Production Readiness Report

**Дата:** 2026-09-14  
**Репозиторий:** `JoTalbot/ukraine`  
**Аудит:** production readiness / fail-closed release control

## Итог

**Control plane: GREEN по архитектуре и контрактам. Полный data product: NOT YET CERTIFIED.**

Production намеренно остаётся **RED / fail-closed**: discovery bootstrap не завершён, реального production artifact/evaluation evidence недостаточно, а authoritative production authorization не оформлена для конкретного проверенного release.

## Шаг 1 — Повторная проверка production readiness

Проверены readiness gate, hardening, artifact chain, promotion authorization, discovery state и release-control workflow. Readiness связывает promotion gate с реальным verifier авторизации, включая проверку существования и SHA-256 production artifact и evaluation evidence.

Это закрывает semantic gap: одного корректного JSON authorization недостаточно, если указанные реальные файлы не существуют или их содержимое изменилось.

## Шаг 2 — Security path safety

`verify_promotion_authorization.py` принимает только относительные пути внутри `artifacts/`, запрещает абсолютные пути и `..`, после `resolve()` проверяет принадлежность корню репозитория. Это fail-closed поведение.

## Шаг 3 — Discovery publication truthfulness

В `.github/workflows/discovered-open-data-huggingface.yml` сохранение progress отделено от финального failure. Если batch содержит failed resources, progress сначала фиксируется, затем job получает `failure`, после чего `always()` publication signal становится RED.

Предыдущий runtime run `34848512473` подтвердил это поведение: batch обработан, обнаружено 53 failed resources, `Persist bootstrap progress` завершился успешно, состояние было отправлено в `main`, после чего job намеренно завершился с `exit 1`.

## Шаг 4 — Исправление starvation в scheduler

Найдена отдельная liveness-ошибка: при наличии любого `failed_batches` scheduler всегда выбирал минимальный failed batch и мог бесконечно не доходить до ещё не проверенных batch.

Исправлено в commit `d726ad9251ed119bf9dd616a04e49fe84a89a233`: при bootstrap сначала выбирается первый **неуспешный и ещё не падавший** batch; retry failed batches начинается только после исчерпания всех непроверенных batch.

Regression test зафиксирован в commit `22f30ccc071754477502c5518bdb5c770a8ae926`.

## Шаг 5 — Discovery state и проверка продвижения

Текущее проверенное состояние `main`:

- `batch_count=360`;
- `failed_batches=0..21`;
- `successful_batches=[]`;
- `completed_batches=0`;
- `next_batch=22`;
- `bootstrap_complete=false`;
- последний timestamp состояния: `2026-09-14T14:41:08.070554+00:00`.

Это подтверждает продвижение scheduler с batch `21` до следующего непроверенного batch `22`, несмотря на наличие failed batches. Ни один failed batch искусственно успешным не объявлялся. fileciteturn319file0

## Шаг 6 — Причина текущих data failures

Runtime evidence показывает два класса внешних проблем источников:

- `data.gov.ua`: HTTP `429 Too Many Requests` на части ресурсов;
- `opendata.gov.ua`: `ConnectTimeout` при скачивании части ресурсов.

Это реальные source-side availability/rate-limit failures. Pipeline корректно учитывает их как failed resources, сохраняет progress и оставляет publication RED.

## Шаг 7 — Усиление retry/backoff

В discovery downloader реализованы:

- HTTP `408`, `425` и `429` как retryable;
- все `5xx` как retryable;
- использование числового `Retry-After`, если он присутствует;
- **новое:** разбор стандартного HTTP-date формата `Retry-After`;
- ограничение задержки через `DATA_GOV_MAX_RETRY_WAIT` с default 60 секунд;
- exponential backoff при отсутствии корректного `Retry-After`;
- удаление частичного файла перед следующей попыткой;
- сохранение ресурса в failed после исчерпания попыток.

Изменение `88b7376845ffe3812832f769dbd9836cb6b8133f` усиливает взаимодействие с rate-limited источниками, не превращая временную недоступность в ложный успех.

## Шаг 8 — CI и исправление обнаруженных ошибок

CI run `34856112949` / `Ukraine data CI #529` ранее выявил синтаксическую ошибку в failure log и Ruff `RUF012` в retry tests. Они исправлены commits `f65b464fc655cf81ec583448c18816e223c14223` и `70dbb97c33bc3ee23fe206bd2e3d3963008720c5`.

Новый CI run `34856558232` на `70dbb97c33bc3ee23fe206bd2e3d3963008720c5` подтвердил:

- Ruff — GREEN;
- compileall — GREEN;
- unit tests — **140 passed, 1 skipped**;
- release manifest — GREEN;
- SBOM — GREEN;
- status index — GREEN;
- release contract — GREEN;
- production hardening self-test — GREEN.

Run завершился RED только на `Verify authoritative promotion authorization`, потому что отсутствует `artifacts/status/production-promotion-authorization.json`. Это ожидаемый fail-closed production gate, а не дефект retry-кода. fileciteturn328file0

После этого выполнено новое изменение retry-after: commit `690d283d3a48a66c01b7cd2b4dcbb8b21a1528a8`, добавляющее детерминированный тест HTTP-date `Retry-After`. На момент отчёта GitHub ещё не опубликовал status checks для этого commit.

## Шаг 9 — Остаточные слабые места

### P0

1. Завершить discovery bootstrap: `successful_batches == batch_count`, `failed_batches == []`, `bootstrap_complete=true`.
2. Runtime-проверить дальнейшее продвижение scheduler через batch `22+`.
3. Накопить реальные producer/evaluation evidence.
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
| Discovery scheduler liveness | **GREEN / ИСПРАВЛЕНО + RUNTIME** |
| Rate-limit/timeout retry policy | **GREEN / УСИЛЕНО + TEST** |
| CI syntax/lint/test validation | **GREEN** |
| Cryptographic artifact chain | **УКРЕПЛЕНА, НЕ SIGNED PROVENANCE** |
| Authoritative promotion authorization | **RED / ОТСУТСТВУЕТ** |
| Discovery bootstrap | **RED / НЕ ЗАВЕРШЁН** |
| Real producer evidence | **RED / НЕДОСТАТОЧНО** |
| Deployment rollback evidence | **RED / НЕДОСТАТОЧНО** |
| Full production certification | **RED / NOT YET CERTIFIED** |

## Изменения этого батча

1. `88b7376845ffe3812832f769dbd9836cb6b8133f` — HTTP-date `Retry-After` и retryable `408/425/429`.
2. `690d283d3a48a66c01b7cd2b4dcbb8b21a1528a8` — стабильный regression test HTTP-date retry hint.
3. CI `34856558232` подтвердил 140 passed / 1 skipped и зелёную техническую валидацию до authoritative authorization gate.
4. Discovery state остаётся `next_batch=22`; batches `0..21` остаются честно failed.

## Решение

**PRODUCTION HARDENING IN PROGRESS. CONTROL-PLANE ARCHITECTURE GREEN. FULL DATA PRODUCT NOT YET CERTIFIED.**

Следующий обязательный рубеж: дождаться CI для retry hardening, затем runtime-проверить batch `22+`, оценить фактический эффект Retry-After/backoff и продолжить bootstrap без ослабления fail-closed политики. После завершения discovery нужны реальные producer/evaluation/release evidence, затем защищённое approval и deployment/rollback verification. До этого production должен оставаться заблокированным.
