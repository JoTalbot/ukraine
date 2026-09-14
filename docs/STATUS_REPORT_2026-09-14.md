# Ukraine — Production Readiness Report

**Дата:** 2026-09-14  
**Репозиторий:** `JoTalbot/ukraine`  
**Аудит:** production readiness / fail-closed release control

## Итог

**Control plane: GREEN по архитектуре и контрактам. Полный data product: NOT YET CERTIFIED.**

Production намеренно остаётся **RED / fail-closed**: discovery bootstrap не завершён, реального production artifact/evaluation evidence недостаточно, а authoritative production authorization не оформлена для конкретного проверенного release.

## Шаг 1 — Повторная проверка production readiness

Проверены readiness gate, hardening, artifact chain, promotion authorization, discovery state и release-control workflow. Readiness теперь дополнительно связывает promotion gate с реальным verifier авторизации, включая проверку существования и SHA-256 production artifact и evaluation evidence. fileciteturn145file0

Это закрывает ранее найденный semantic gap: одного корректного JSON authorization недостаточно, если указанные реальные файлы не существуют или их содержимое изменилось.

## Шаг 2 — Security path safety

`verify_promotion_authorization.py` принимает только относительные пути внутри `artifacts/`, запрещает абсолютные пути и `..`, после `resolve()` проверяет принадлежность корню репозитория. Это fail-closed поведение. fileciteturn145file0

## Шаг 3 — Discovery publication truthfulness

В `.github/workflows/discovered-open-data-huggingface.yml` сохранение progress отделено от финального failure. Если batch содержит failed resources, progress сначала фиксируется, затем job получает `failure`, после чего `always()` publication signal становится RED.

Таким образом `continue-on-error` внутреннего mirror-шага больше не может сам по себе превратить неуспешный batch в успешный producer result.

## Шаг 4 — Discovery state

Текущее состояние bootstrap остаётся неполным:

- `batch_count=360`;
- `failed_batches=0..20`;
- `successful_batches=[]`;
- `completed_batches=0`;
- `bootstrap_complete=false`.

Ни один failed batch искусственно успешным не объявлялся.

## Шаг 5 — Реальный runtime gate

Последний наблюдаемый Release Control Plane корректно дошёл до проверки authoritative promotion authorization и остановился на ней. Последующие artifact-chain/readiness стадии были пропущены. Это ожидаемое fail-closed поведение при отсутствии разрешения на production.

## Шаг 6 — Остаточные слабые места

### P0

1. Завершить discovery bootstrap: `successful_batches == batch_count`, `failed_batches == []`, `bootstrap_complete=true`.
2. Получить реальные production artifact и evaluation evidence.
3. Оформлять authorization только для конкретного проверенного release и фактически существующих файлов.

### P1

4. Защитить authorization отдельной approval boundary: protected environment/branch или криптографическая подпись.
5. Добавить независимый signed provenance/attestation.
6. Добавить deployment-side atomic rollback и фактический recovery test.
7. Запустить end-to-end regression CI после изменений readiness verifier-binding и зафиксировать результат в отчёте.

### P2

8. Расширить freshness/retry/recovery observability.
9. Добавить периодическую end-to-end production certification.

## Сертификационная матрица

| Контур | Статус |
|---|---|
| Production architecture | **GREEN** |
| Hardening contracts | **GREEN / УКРЕПЛЕНЫ** |
| Promotion path safety | **GREEN** |
| Readiness → real artifact binding | **GREEN / УСИЛЕНО** |
| Discovery publication truthfulness | **GREEN / УКРЕПЛЕНО** |
| Cryptographic artifact chain | **УКРЕПЛЕНА, НЕ SIGNED PROVENANCE** |
| Authoritative promotion authorization | **RED / ОТСУТСТВУЕТ** |
| Discovery bootstrap | **RED / НЕ ЗАВЕРШЁН** |
| Real producer evidence | **RED / НЕДОСТАТОЧНО** |
| Deployment rollback evidence | **RED / НЕДОСТАТОЧНО** |
| Full production certification | **RED / NOT YET CERTIFIED** |

## Изменения этого батча

1. `cf006f65639534f8095bfffa743540aa1fd03cb6` — readiness gate дополнительно вызывает реальный promotion-authority verifier и требует фактической проверки artifact/evaluation binding.
2. `ddf999d007b14e1c300f480599f0c322fc0a06b9` — discovered-data workflow явно краснеет после сохранения failed batch state.
3. `b330fc3ca5b26792be1b4445008711627536ef9e` — добавлен regression test для failure-order контракта.
4. `11afc0b5db2a044f832c28db183be883d997ec4f` — нормализован discovery progress state.

## Решение

**PRODUCTION HARDENING IN PROGRESS. CONTROL-PLANE ARCHITECTURE GREEN. FULL DATA PRODUCT NOT YET CERTIFIED.**

Следующий обязательный рубеж: реальные producer/evaluation/release evidence, затем защищённое approval и deployment/rollback verification. До этого production должен оставаться заблокированным.
