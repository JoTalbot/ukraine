# Ukraine — Production Readiness Report

**Дата:** 2026-09-14  
**Репозиторий:** `JoTalbot/ukraine`  
**Последний commit этой итерации:** `a24e6736a6f8c5f2a9c1e51e7c9fbf21a2c8e2f8`

## Итог

Проект имеет зрелый набор production-контрактов для provenance, SBOM, reproducibility, drift, quarantine, model registry, compatibility, promotion, rollback и readiness. Однако **production-ready окончательно не подтверждён**: обязательная GitHub Actions цепочка после последних изменений ещё выполняется, а несколько P1-слабых мест требуют усиления.

## Проверено

- READY-01 агрегирует документацию, release manifest, control-plane, recovery, dependency lock, SBOM, provenance и hardening contracts.
- EVID-02 требует runtime evidence непосредственно перед readiness gate во всех workflow, которые вызывают READY-01.
- Release Control Plane и Production Release Gate используют generated readiness evidence.
- GitHub Actions закреплены immutable commit SHA.
- `requirements.lock` существует и содержит детерминированный CI baseline.
- Kaggle finetune patch исправлен: HF publication failure теперь оборачивается корректным `try` с вложенным `if`, чтобы ошибка публикации не превращала успешное обучение в `KernelWorkerStatus.ERROR`.

## Найденные слабые места

### P0 — runtime ещё не сертифицирован

`Ukraine data CI`, `Release Control Plane` и `Production Release Gate` после изменений были запущены цепочкой, но на момент отчёта не завершили полный зелёный проход. Поэтому финальный production verdict остаётся **PENDING VERIFICATION**.

### P1 — readiness ранее доверял наличию файлов

READY-01 проверял наличие release manifest/status index и hardening script, но не связывал runtime evidence с конкретным release manifest. Это создавало возможность принять evidence другого commit.

**Исправлено:** readiness теперь требует валидную схему evidence, identity и совпадение `source_commit` с `release-manifest.git_commit`; добавлены regression tests.

### P1 — freshness policy могла быть формально неполной

Проверка freshness использовала truthiness и не гарантировала корректную структуру окон.

**Исправлено:** readiness требует непустую mapping-структуру с положительными числовыми окнами; добавлен отрицательный тест.

### P1 — promotion policy пока документальный

`promotion_policy` фактически становится green при наличии `docs/PRODUCTION_READINESS.md`. Это не доказывает, что production promotion реально выполнен через registry/promotion contract.

**Улучшение:** связать readiness с машинно-читаемым promotion record: candidate model ID, artifact SHA-256, evaluation evidence SHA, compatibility result, approval identity/time и target `production`.

### P1 — rollback зависит от порядка registry

`ROLL-01` выбирает последний production model по порядку элементов registry. Для production надёжнее использовать immutable promotion timestamp/version.

**Улучшение:** хранить `promoted_at`, monotonic release sequence и immutable production event; выбирать rollback по ним.

### P1 — quarantine не полностью immutable

Digest-qualified имя хорошо защищает от путаницы, но повторная запись в тот же путь пока не запрещена.

**Улучшение:** при существующем объекте сравнивать SHA-256 и отказывать при несовпадении; предпочтительно использовать content-addressed storage/manifest.

### P1 — checksum chain не проверяется целиком

READY-01 связывает evidence с commit, но ещё не пересчитывает и не сверяет SHA-256 всей цепочки release manifest → SBOM → status signals → hardening evidence.

**Улучшение:** добавить cryptographic artifact binding для каждого входного артефакта.

### P2 — discovery не завершён

Последнее зафиксированное состояние discovery показывало `bootstrap_complete=false`, `next_batch=21`, `completed_batches=21` из `batch_count=360`, при failed batches 0–20. Следовательно, ingestion ещё нельзя считать полностью закрытым.

## Выполнено в этой итерации

1. Усилен `scripts/check_production_readiness.py`.
2. Добавлены тесты на mismatch release/evidence identity.
3. Добавлен тест на пустую freshness policy.
4. Исправлен Kaggle notebook patcher для валидного Python `try/if` блока.
5. В `docs/ROADMAP.md` добавлены READY-02, KAG-01 и приоритеты следующего hardening этапа.
6. Этот отчёт сохранён в репозитории.

## Runtime status

- `Ukraine data CI`: выполнялся после изменений.
- `Release Control Plane`: выполнялся цепочкой после producer/CI событий.
- `Production Release Gate`: был поставлен в цепочку после Release Control Plane.
- Финальный verdict: **HARDENED / NOT YET CERTIFIED**.

## Следующий production batch

1. Подтвердить green `Ukraine data CI`.
2. Подтвердить green `Release Control Plane`.
3. Подтвердить green `Production Release Gate`.
4. Проверить Kaggle FT rerun и results collector.
5. Ввести cryptographic artifact binding.
6. Усилить promotion, rollback и quarantine semantics.
7. Закрыть failed discovery batches и подтвердить `bootstrap_complete=true`.
8. Только после этого объявить production-ready.

## Решение

**Статус: HARDENED / NOT YET CERTIFIED.**

Архитектура уже близка к production, но сертификат нельзя выдавать, пока тесты ещё бегут. Люди почему-то любят именно такой порядок действий, поэтому здесь порядок будет обратным: сначала доказательства, потом печать диплома.
