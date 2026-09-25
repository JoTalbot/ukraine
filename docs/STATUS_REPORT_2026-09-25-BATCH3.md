# Ukraine — Production Readiness Report

**Дата:** 2026-09-25 (батч 3)  
**Репозиторий:** `JoTalbot/ukraine`  
**Аудит:** шаг 3 — discovery bootstrap в песочнице (решение владельца (в)): батч 96 прогнан в `--dry-run`

## Итог

**Bootstrap в песочнице работает: батч 96 прогнан (dry-run): 98 ресурсов скачано и проверено (SHA-256), 2 реальных отказа (403 у источников), 0 blocked. State обновлён по правилам проекта: next_batch=97, failed=44. Батч 96 в retry-очереди — CI (с HF_TOKEN) добъёт зеркалирование и проставит легитимный successful. Production: RED / fail-closed намеренно (bootstrap_complete=false).**

В песочнице нет HF_TOKEN → синхронизация выполнена в `--dry-run` (документированный флаг скрипта: скачать + SHA-256-проверка, без загрузки). Имитация публикаций запрещена: «чистый» dry-run батч НЕ помечается `successful` (dry-run-страж).

## Шаги

### Шаг 1 — Этап 0 (ситуация (в) + дрейф окружения)
- origin восстановлен по стартеру; identity сброшен; 11 скриптов возвращены в 755 (сброс режимов снапшотом, урок 13); porcelain=0.
- Окружение дёрнулось после снапшота (pytest 9.0.3 против канонических 9.1.1) → переустановка по lock: ruff 0.16.5, pytest 9.1.1, pyarrow 25.0.1.
- Дистанция впереди локальной: CI запушил `ba9371b chore(data): persist discovered open-data progress` (state: батч 95, next_batch=96) → fast-forward pull.

### Шаг 2 — Пайплайн bootstrap (команды workflow, отклонения песочницы помечены)
- Каталог: `data_gov_ua_discovery.py --output … --status-output … --fallback-on-error --limit 0` → **3585 датасетов** (свежий; CKAN API data.gov.ua из песочницы доступен, проба 0.9s).
- Выбор батча (алгоритм workflow): **batch=96, mode=bootstrap, offset=960, size=10** (совпадает с next_batch=96 state).
- Зеркалирование: `data_gov_ua_discovered_sync.py --dataset-offset 960 --dataset-limit 10 --incremental --allow-failures --dry-run` (отклонения: `--dry-run` — нет HF_TOKEN; артефакты — вне репо).
- Результат (BATCH SUMMARY): datasets=10, downloaded=98, resource_failures=2, blocked_resources=0, unreachable_hosts=[].
- Отказы (реальные, resource_error): `data.rada-uzhgorod.gov.ua …/services.csv`; `opendata.slavuta-mvk.gov.ua …/budpasport.csv` (403 FORBIDDEN, 3 попытки).

### Шаг 3 — Персист progress (логика workflow)
- failed_count=2 > 0 → `failed_batches += [96]`; successful/blocked без изменений; next_batch = первый невидимый = 97; last_batch={96, bootstrap, failed_resources=2, blocked_resources=0}; bootstrap_complete=false.
- Перед записью — ff-merge актуального origin/main (новых коммитов CI не было); коммит `chore(data): persist discovered open-data progress` (сообщение — по конвенции CI; identity — Arena Agent, а не github-actions[bot]).
- Свежий каталог (3585) — **не коммитится** (CI делает то же; копия в репо — fallback-снапшот из 500 датасетов): восстановлен HEAD-состояние, свежая копия — `/home/user/work/catalog-fresh-step3.json`.

### Шаг 4 — Тесты после правок (все профили)
| Профиль | Результат |
|---|---|
| P1 lint | RC=0, «All checks passed!» |
| P2 compile | RC=0 |
| P3 тесты (полный) | 170 passed, 1 skipped (skipped = torch, штатно) |
| P4 контракт графа | 6 passed |
| P5 CI smoke-цепочка | RC=0 ×6, «Release contract OK» |

## Остаточные слабые места

1. Батч 96 не завершён (2 ресурса: 403/ошибка у муниципальных сайтов) → в retry-очереди; CI с HF_TOKEN перезеркалирует (или вручную: workflow_dispatch `batch_index=96`).
2. bootstrap_complete=false: next_batch=97 из 359; failed=44, blocked=53, successful=0, completed=0.
3. Песочница не может дать «successful» батч (нет HF_TOKEN) — dry-run-страж: чистый dry-run батч не помечается успешным (урок 21).
4. `opendata.gov.ua` сломан с 2026-09-14 (TLS-хендшейк висит) — blocked-батчи (53) не разблокируются до возвращения источника.

## Изменения

| Файл | Изменение |
|---|---|
| `.github/state/discovered-open-data-progress.json` | батч 96 → failed (2 ресурса), next_batch=97, last_batch обновлён |
| `docs/STATUS_REPORT_2026-09-25-BATCH3.md` | создан (данный отчёт) |
| `docs/AGENT_CANON.md` | «ТОЧКА ВОЗОБНОВЛЕНИЯ» (шаг 3), урок 21 (sandbox dry-run bootstrap) |

Код не менялся: `scripts/`, `tests/`, `schemas/`, `.github/` не тронуты.

## Решение

STEP 3 COMPLETE: discovery bootstrap in sandbox — batch 96 run (dry-run), 2 real failures recorded, state current (next_batch=97), no success emulation.

Дальше (в песочнице): батчи 97+ (dry-run) и/или retry-очередь failed (44). Целевое зеркалирование батча 96 с публикацией — действие владельца/CI (workflow_dispatch `batch_index=96`). Fail-closed не ослабляется.
