# Ukraine — Production Readiness Report

**Дата:** 2026-09-14  
**Репозиторий:** `JoTalbot/ukraine`  
**Последний hardening batch:** `8054ecec2e8e59fbde96250cad00b03bd8fd7a73`

## Итог

**Control plane: GREEN по архитектуре и контрактам. Полный data product: NOT YET CERTIFIED.**

В этом batch production-контур усилен непосредственно в репозитории: добавлена криптографическая artifact chain, ужесточены quarantine/promotion/rollback, readiness теперь требует эти gates, CI запускает проверки в правильном порядке, а discovery перестал считать попытки успешными batch-ами.

При этом фактическая production-сертификация должна ждать успешного CI после этих изменений и полного завершения discovery bootstrap. GitHub Actions должны подтвердить код на реальном runner, потому что даже человечество иногда обнаруживает синтаксические ошибки только после запуска.

## Шаг 1 — Production readiness audit

Проверены `scripts/check_production_readiness.py`, `scripts/production_hardening.py`, production CI и release observability. До batch-а READY-01 проверял наличие hardening-кода и identity evidence, но не обеспечивал полноценную cryptographic chain и реальный promotion event.

## Шаг 2 — Cryptographic artifact chain

Добавлен `scripts/verify_artifact_chain.py`.

Он:
- проверяет SHA-256 всех файлов, перечисленных release manifest;
- проверяет наличие и целостность release manifest, SBOM, status index и hardening evidence;
- сверяет commit identity hardening evidence с release manifest;
- требует зелёные hardening contracts;
- формирует `artifacts/status/artifact-chain.json`;
- не создаёт циклическую зависимость, поскольку chain является отдельным итоговым binding-артефактом.

## Шаг 3 — Promotion / rollback / quarantine

`production_hardening.py` усилен:

- **QUAR-01:** имя quarantine теперь использует полный SHA-256; существующий объект проверяется перед повторным использованием; checksum копии проверяется после записи.
- **PROM-01:** production promotion требует `model_id`, artifact SHA-256, evaluation-evidence SHA-256, approval identity, положительный `release_sequence` и `promoted_at`; создаётся machine-readable promotion event.
- **ROLL-01:** rollback принимает только production targets с immutable `release_sequence` и `promoted_at`, выбирает последний по sequence/time и fail-closed при отсутствии валидного target.
- Runtime hardening evidence теперь содержит negative tests для tampered quarantine object и promotion без обязательной metadata.

## Шаг 4 — READY-01

Production readiness теперь требует:

1. runtime hardening evidence;
2. успешные negative tests;
3. cryptographic artifact chain;
4. authoritative promotion event.

Простое наличие `docs/PRODUCTION_READINESS.md` больше не считается достаточным promotion gate.

## Шаг 5 — CI

`ukraine-data-ci.yml` и `release-observability.yml` получили последовательность:

`release manifest → SBOM/status → hardening evidence → artifact-chain verification → READY-01 → tests/upload`.

Artifact chain загружается вместе с остальными release-status артефактами.

## Шаг 6 — Discovery state correctness

Исправлен bootstrap state contract.

Раньше `completed_batches` фактически мог означать количество обработанных попыток, даже когда соответствующие batch-ы находились в `failed_batches`. Теперь состояние различает:

- `successful_batches`;
- `failed_batches`;
- `completed_batches` как количество успешных batch-ей;
- `bootstrap_complete=true` только когда успешны все batch-и и нет failed batch-ей.

Текущее историческое состояние с failed batches не должно автоматически считаться завершённым.

## Шаг 7 — Tests

Расширены production hardening tests:

- authoritative promotion metadata;
- tampered quarantine rejection;
- immutable rollback ordering;
- negative evidence tests;
- artifact-chain/readiness gates;
- проверка порядка CI: hardening → chain → readiness.

## Текущий verdict

| Контур | Статус |
|---|---|
| Production architecture | **GREEN** |
| Release manifest | **GREEN** |
| SBOM / provenance | **GREEN** |
| Control plane contract | **GREEN** |
| Hardening contracts | **УКРЕПЛЕНО** |
| Cryptographic artifact chain | **ДОБАВЛЕНА** |
| Authoritative promotion contract | **ДОБАВЛЕН** |
| Quarantine immutability check | **ДОБАВЛЕН** |
| Rollback ordering contract | **ДОБАВЛЕН** |
| CI integration | **ОБНОВЛЕНО** |
| Discovery bootstrap | **НЕ ЗАКРЫТ** |
| Реальная production-сертификация после batch-а | **ТРЕБУЕТ НОВОГО GREEN RUN** |

## Оставшиеся P0/P1 задачи

1. Дождаться/проверить новый полный CI run после всех изменений.
2. Проверить release observability run на том же commit.
3. Проверить production gate после нового control-plane результата.
4. Завершить failed discovery batches и получить `bootstrap_complete=true`.
5. Подключить реальный deployment-side atomic switch для rollback, потому что текущий контракт формирует безопасный план, но не может сам физически заменить production artifact.
6. Привязать фактический evaluation artifact к promotion event, а не только к deterministic self-test fixture.
7. После этого провести финальный production certification.

## Решение

**Сейчас: PRODUCTION HARDENING IN PROGRESS / CONTROL-PLANE ARCHITECTURE GREEN.**

**Полный data product: NOT YET CERTIFIED.**

Архитектурные слабые места из предыдущего аудита закрыты или существенно усилены. Главные оставшиеся риски теперь операционные: реальный успешный runner после изменений, завершение discovery и фактическое deployment-side выполнение promotion/rollback. 
