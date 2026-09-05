# Ukraine Open Legal & Public Data

[![Ukraine data CI](https://github.com/JoTalbot/ukraine/actions/workflows/ukraine-data-ci.yml/badge.svg)](https://github.com/JoTalbot/ukraine/actions/workflows/ukraine-data-ci.yml)
[![Kaggle Kernel Results](https://github.com/JoTalbot/ukraine/actions/workflows/kaggle-results.yml/badge.svg)](https://github.com/JoTalbot/ukraine/actions/workflows/kaggle-results.yml)
[![EDRSR → HF](https://github.com/JoTalbot/ukraine/actions/workflows/edrsr-huggingface.yml/badge.svg)](https://github.com/JoTalbot/ukraine/actions/workflows/edrsr-huggingface.yml)
[![Train Ukraine Models](https://github.com/JoTalbot/ukraine/actions/workflows/train-models.yml/badge.svg)](https://github.com/JoTalbot/ukraine/actions/workflows/train-models.yml)

Проект воспроизводимого AI-ready pipeline открытых данных Украины: от официальных источников до датасетов на Hugging Face, графа связей и обученных моделей.

## Контур

```text
data.gov.ua → discovery → download → SHA-256 → normalize → Parquet → Hugging Face
                                                                    ↓
                                              entity-link graph
                                                                    ↓
                                              corpus → LM training
                                                                    ↓
                                              evaluation → release
```

## Публичные артефакты

| Артефакт | Ссылка | Объём |
|---|---|---|
| ЄДРСР — судовые решения 2006–2026 | [JoTalbot/ua-edrsr](https://huggingface.co/datasets/JoTalbot/ua-edrsr) | 21 год, Parquet |
| Открытые данные | [JoTalbot/ua-open-data](https://huggingface.co/datasets/JoTalbot/ua-open-data) | официальные открытые наборы |
| Українська legal-LM | [JoTalbot/ua-legal-lm](https://huggingface.co/JoTalbot/ua-legal-lm) | GPT, обучена с нуля |
| Граф связей сущностей | [JoTalbot/ua-entity-graph](https://huggingface.co/datasets/JoTalbot/ua-entity-graph) | entities/mentions/edges |

## Состав

- `scripts/` — ingestion, нормализация, корпус, обучение, entity linkage и release validation.
- `config/` — каталоги источников и приоритетов.
- `schemas/` — канонические схемы.
- `training/kaggle/` — GPU training.
- `docs/` — архитектура, data quality, provenance, evaluation, observability, security и roadmap.
- `tests/` — unit/contract tests.

## Автоматизация

Работают discovery, зеркалирование в HF, EDRSR, CPU/GPU training, Kaggle result collection, entity graph, Pages dashboard, failure alerts и CI. Дополнительно введён отдельный **Release observability** workflow, который регулярно проверяет production contract.

## Production contract

Каждый release должен быть проверяемым, трассируемым, воспроизводимым и безопасным. Минимум: источник, время получения, версия/ETag когда доступно, SHA-256, revision трансформации, идентичность артефакта, лицензия и результаты quality/evaluation gates.

Подробные правила:

- `docs/ROADMAP.md` — единая дорожная карта и Definition of Done.
- `docs/DATA_QUALITY.md` — data contracts и quality gates.
- `docs/REPRODUCIBILITY.md` — provenance и replay protocol.
- `docs/MODEL_EVALUATION.md` — правила оценки моделей.
- `docs/OBSERVABILITY.md` — operational signals и failure semantics.
- `docs/SECURITY.md` — security/privacy checklist.

## Приватность

Используются только законно опубликованные открытые данные (`public_open_data_only`). Не собираются банковская тайна, закрытые телеком-данные, учётные данные или утечки; обезличивание физических лиц, предусмотренное источником, сохраняется и не обращается (`no_deanonymization`).

## Репозитории и роли

- `JoTalbot/ukraine` — ingestion, схемы, граф связей, обучение, evaluation и публикация.
- `JoTalbot/UASEP` — автономная разработка и maintenance automation.

## Лицензия

Код — MIT (см. `LICENSE`). Данные и производные артефакты остаются под лицензиями первоисточников. При переиспользовании сохраняйте атрибуцию источника.
