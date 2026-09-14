# Ukraine — Production Readiness Report

**Дата:** 2026-09-14  
**Репозиторий:** `JoTalbot/ukraine`  
**Проверяемый commit:** `168182133e5ab9f9a7d93f7018f0d6ea2e1fed30`

## Итог

**Control-plane production readiness: GREEN.** Последовательность `Ukraine data CI` → `Release Control Plane` → `Production Release Gate` для проверяемого commit завершилась успешно. Это подтверждает готовность автоматизированного release/control-plane контура, но не означает, что весь data product полностью закрыт: discovery и часть внешних producer-процессов продолжают работу.

## Шаг 1 — Проверка CI

`Ukraine data CI`, run `34812705342`, job `validate` завершён со статусом **success**. Успешно выполнены lint, компиляция, unit-тесты, release manifest, SBOM, status index, contract validation, runtime hardening evidence и production readiness.

## Шаг 2 — Проверка Control Plane

`Release Control Plane`, run `34812726855`, job `aggregate` завершён **success**. Проверены checkout исходного release, deterministic lock, release manifest, producer identity, producer signal, SBOM, canonical status index, control-plane validation, runtime hardening evidence и readiness.

## Шаг 3 — Проверка Production Gate

`Production Release Gate`, run `34812771316`, job `gate` завершён **success**. Gate подтвердил результат control plane и соответствие текущих release manifest/control-plane identity.

## Шаг 4 — Что найдено как слабое место

### P1 — Promotion пока недостаточно авторитетен

`promotion_policy` в READY-01 всё ещё в основном документальный. Наличие документа не доказывает реальное production promotion.

**Нужно:** machine-readable promotion event с `model_id`, artifact SHA-256, evaluation evidence SHA-256, compatibility result, approval identity/time, target и immutable sequence.

### P1 — Rollback зависит от структуры registry

Текущий ROLL-контракт выбирает последний production объект по порядку списка registry. Это слабее, чем явные immutable `release_sequence` + `promoted_at`.

**Нужно:** выбирать last-known-good только по immutable promotion metadata и выполнять фактический атомарный switch артефакта/ссылки.

### P1 — Quarantine требует строгой content-addressed семантики

Digest-qualified имя полезно, но production-контракт должен явно запрещать изменение уже существующего объекта с тем же digest-qualified путём.

**Нужно:** при существующем объекте пересчитывать SHA-256 и отклонять mismatch; публиковать manifest объекта.

### P1 — Полная checksum chain ещё не является отдельным gate

Evidence уже привязывается к release commit, но readiness не является полноценной криптографической проверкой цепочки `release manifest → SBOM → signals → hardening evidence`.

**Нужно:** хранить и проверять SHA-256 каждого входного артефакта перед promotion.

### P2 — Discovery/data ingestion не закрыты полностью

Ранее зафиксированное состояние discovery показывало `bootstrap_complete=false`, `next_batch=21`, `completed_batches=21` из `batch_count=360`, при failed batches 0–20. Поэтому полный data-product production certification пока преждевременен.

## Шаг 5 — Что уже усилено

1. READY-01 проверяет schema и release/evidence identity.
2. Freshness policy валидируется структурно и fail-closed.
3. Добавлены regression tests для identity mismatch и invalid freshness policy.
4. Исправлен Kaggle notebook patcher с корректной Python indentation для non-fatal HF publication.
5. Runtime hardening evidence выполняется непосредственно перед readiness gate.
6. GitHub Actions используют immutable action references там, где это предусмотрено политикой.
7. Recovery checkpoints и deterministic replay manifest проходят отдельный CI-контроль.

## Шаг 6 — Текущий production verdict

| Контур | Статус |
|---|---|
| Unit/lint/compile CI | **GREEN** |
| Release manifest | **GREEN** |
| SBOM | **GREEN** |
| Canonical control plane | **GREEN** |
| Runtime hardening evidence | **GREEN** |
| Production Release Gate | **GREEN** |
| Полная discovery/data ingestion | **НЕ ЗАКРЫТА** |
| Полная криптографическая artifact chain | **УСИЛИТЬ** |
| Авторитетный promotion/rollback | **УСИЛИТЬ** |

## Шаг 7 — Следующий production batch

1. Сделать promotion event обязательным machine-readable контрактом.
2. Добавить immutable `release_sequence` и `promoted_at` в model registry/promotion.
3. Добавить cryptographic binding для всех release/control-plane artifacts.
4. Закрыть quarantine overwrite/mismatch path.
5. Добавить negative tests для tampered artifact, stale signal, checksum mismatch и rollback без last-known-good.
6. Завершить failed discovery batches и добиться `bootstrap_complete=true`.
7. Проверить scheduled EDRSR/Hugging Face producer после завершения текущего запуска.

## Решение

**CONTROL PLANE: PRODUCTION READY / GREEN.**  
**FULL DATA PRODUCT: NOT YET CERTIFIED.**

То есть пульт управления уже можно выпускать в production, а вот объявлять весь украинский data pipeline законченным было бы преждевременно. Машины завелись, но груз ещё не весь погружен.
