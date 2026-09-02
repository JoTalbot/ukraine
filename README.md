# Ukraine Open Legal & Public Data

[![Ukraine data CI](https://github.com/JoTalbot/ukraine/actions/workflows/ukraine-data-ci.yml/badge.svg)](https://github.com/JoTalbot/ukraine/actions/workflows/ukraine-data-ci.yml)
[![Kaggle Kernel Results](https://github.com/JoTalbot/ukraine/actions/workflows/kaggle-results.yml/badge.svg)](https://github.com/JoTalbot/ukraine/actions/workflows/kaggle-results.yml)
[![EDRSR → HF](https://github.com/JoTalbot/ukraine/actions/workflows/edrsr-huggingface.yml/badge.svg)](https://github.com/JoTalbot/ukraine/actions/workflows/edrsr-huggingface.yml)
[![Train Ukraine Models](https://github.com/JoTalbot/ukraine/actions/workflows/train-models.yml/badge.svg)](https://github.com/JoTalbot/ukraine/actions/workflows/train-models.yml)

Проект воспроизводимого AI-ready pipeline открытых данных Украины:
от официальных источников до датасетов на Hugging Face, графа связей и обученных моделей.

## Контур (работает)

```
data.gov.ua → discovery → скачивание → SHA-256 → нормализация → Parquet → Hugging Face
                                                                    ↓
                                              граф связей сущностей (entity linkage)
                                                                    ↓
                                              корпус → обучение LM (CPU CI + GPU Kaggle)
                                                                    ↓
                                              публикация моделей в Hugging Face Hub
```

## Публичные артефакты

| Артефакт | Ссылка | Объём |
|---|---|---|
| ЄДРСР — судовые решения 2006–2026 | [JoTalbot/ua-edrsr](https://huggingface.co/datasets/JoTalbot/ua-edrsr) | 21 год, Parquet |
| Открытые данные (27 наборов) | [JoTalbot/ua-open-data](https://huggingface.co/datasets/JoTalbot/ua-open-data) | ЄДР, ПДВ, декларації, санкції… |
| Українська legal-LM | [JoTalbot/ua-legal-lm](https://huggingface.co/JoTalbot/ua-legal-lm) | GPT, обучена с нуля |

## Состав репозитория

- `scripts/` — синхронизация данных (`data_gov_ua_*`, `edrsr_sync.py`), сборка корпуса
  (`build_lm_corpus.py`), обучение (`train_lm.py`), граф связей (`entity_links.py`)
- `config/` — каталог зеркалируемых наборов и реестр приоритетных источников
- `schemas/` — канонические схемы данных и графа связей
- `training/kaggle/` — GPU-кернел для Kaggle T4
- `docs/` — архитектура, пайплайн ЄДРСР, entity linkage, разбор источников imena.ua (2015)
- `tests/` — юнит-тесты (парсер, граф, LM); запускаются в CI

## Автоматизация (GitHub Actions)

| Workflow | Расписание | Что делает |
|---|---|---|
| Ukraine Open Data Discovery | ежедневно | обнаружение наборов data.gov.ua |
| Ukraine Open Data → HF | 2×/день | зеркалирование каталога |
| Discovered Open Data → HF | по событию | зеркалирование найденных наборов |
| EDRSR → HF | каждые 30 мин | годы 2006–2026, skip по ETag, параллельная матрица |
| Train Ukraine Models | 2×/день | корпус → GPT на CPU → публикация в HF Hub |
| Kaggle GPU Training | 2×/неделю + при изменении кода обучения | push GPU-кернела (статус-чек активной версии, защита GPU-квоты) |
| Kaggle Kernel Results | каждые 15 мин | автосбор результатов и публикация моделей |
| Ukraine data CI | на push | pytest + compileall + контракт репозитория |
| Workflow Failure Alerts | по завершению | авто-issue при падении, закрытие при восстановлении |

## Граф связей

`scripts/entity_links.py` строит и опрашивает граф: сущности (ЄДРПОУ / ІПН / имена),
упоминания в базах, рёбра (учредитель, подписант, судья↔суд, соистцы). Демо на реальных
данных: 4,4 млн сущностей, 4,9 млн рёбер. Подробнее — `docs/ENTITY_LINKS.md`.

## Приватность

Используются только законно опубликованные открытые данные. Не собираются банковская
тайна, закрытые телеком-данные, учётные данные, утечки; обезличивание физических лиц,
предусмотренное источником, сохраняется и не обращается (`no_deanonymization`).

## Репозитории и роли

- `JoTalbot/ukraine` — ingestion, схемы, граф связей, обучение, публикация.
- `JoTalbot/UASEP` — автономная разработка и maintenance automation.

## Лицензия

Код — MIT (см. `LICENSE`). Данные и производные артефакты остаются под лицензиями
первоисточников (data.gov.ua — преимущественно CC BY; решения ЄДРСР — официальные
публичные документы). При переиспользовании данных сохраняйте атрибуцию источника.
