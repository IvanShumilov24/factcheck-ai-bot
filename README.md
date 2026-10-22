# Правда под вопросом

Telegram-бот для проверки достоверности медицинской информации по внешним источникам.

Пользователь отправляет текст, ссылку или изображение с текстом. Бот выделяет отдельные
проверяемые утверждения, находит медицинские источники, извлекает фрагменты доказательств,
сравнивает их с утверждением и формирует осторожный вывод с объяснением и ссылками.

Бот не ставит диагнозы, не назначает лечение и не заменяет консультацию врача.

## Возможности

- проверка текста, URL и изображений со скриншотами текста;
- OCR через заменяемый провайдер;
- выделение нескольких claims из одного материала с сохранением контекста и отрицаний;
- классификация утверждений: факт, медицинское утверждение, совет, мнение, опыт;
- генерация поисковых запросов и поиск через Yandex Search API;
- ранжирование источников по качеству, авторитетности и релевантности;
- извлечение evidence из содержимого страниц;
- анализ отношений `SUPPORTS`, `CONTRADICTS`, `NEUTRAL`;
- консервативные verdict: подтверждено, частично подтверждено, не подтверждается,
  противоречит данным, недостаточно данных, конфликтующие данные;
- отдельный просмотр доказательств и источников;
- история проверок пользователя с пагинацией;
- `/demo` без внешних API;
- `/cancel` для отмены активной проверки;
- пять коротких уроков по самостоятельной проверке медицинской информации;
- rate limit, кэширование, дедупликация и повторные попытки внешних запросов;
- Redis Streams worker для длительных проверок.

## Архитектура

```text
Telegram / aiogram
        ↓
handlers и keyboards
        ↓
ContentPreparationService
        ↓
ClaimExtractionService
        ↓
SearchQueryGenerator → SearchProvider → SourceSearchService
        ↓
EvidenceExtractionService → EvidenceAnalysisService
        ↓
EvidenceMatrixService → VerdictService
        ↓
Report / PostgreSQL / Telegram
```

Длительные проверки выполняются асинхронно:

```text
Telegram handler
        ↓
PostgreSQL: Check(QUEUED)
        ↓
Redis Streams
        ↓
worker
        ↓
FactCheckPipeline
        ↓
PostgreSQL: COMPLETED / FAILED / CANCELLED
        ↓
Telegram report
```

Бизнес-логика отделена от Telegram, LLM, поиска, OCR и хранения. Провайдеры подключаются
через протоколы и могут заменяться без переписывания pipeline.

## Стек

- Python 3.12+;
- aiogram 3;
- Pydantic 2;
- SQLAlchemy 2 и PostgreSQL;
- Redis и Redis Streams;
- Alembic;
- httpx, BeautifulSoup4;
- OpenRouter Chat Completions со structured output;
- Claude Haiku как основная LLM-модель через OpenRouter;
- Yandex Search API v2;
- Docker Compose;
- pytest, Ruff и mypy.

## Структура проекта

```text
app/
├── bot/                  # Telegram handlers и inline-клавиатуры
├── core/                 # исключения и общие правила
├── database/             # SQLAlchemy Base, модели и session factory
├── domain/               # доменные модели, enum и Pydantic schemas
├── repositories/         # persistence layer
├── services/
│   ├── claims/           # выделение и нормализация утверждений
│   ├── education/        # образовательные уроки
│   ├── evidence/         # evidence, coverage, matrix и verdict
│   ├── extraction/       # текст и URL
│   ├── factcheck/        # адаптер общего fact-check интерфейса
│   ├── llm/              # LLM providers
│   ├── ocr/              # OCR providers
│   ├── search/            # запросы, поиск, нормализация и ranking
│   ├── content.py        # подготовка входного материала
│   ├── pipeline.py       # основной pipeline
│   ├── queue.py          # Redis Streams queue
│   ├── ratelimit.py      # ограничение частоты запросов
│   └── report.py         # пользовательские отчёты
├── main.py               # Telegram polling process
└── worker.py             # фоновый worker
alembic/                  # миграции базы данных
tests/                    # unit и integration-oriented тесты
```

## Установка

Требования: Python 3.12+, PostgreSQL и Redis.

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
cp .env.example .env
```

Заполните в `.env`:

```env
BOT_TOKEN=
OPENROUTER_API_KEY=
OPENROUTER_MODEL=anthropic/claude-haiku-5.5
YANDEX_API_KEY=
YANDEX_FOLDER_ID=
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/factcheck
REDIS_URL=redis://localhost:6379/0
```

Остальные параметры ограничений, timeout, proxy, cache и worker находятся в `.env.example`.

## Запуск через Docker Compose

```bash
cp .env.example .env
docker compose up -d --build
docker compose exec bot alembic upgrade head
```

Compose запускает:

- `bot` — Telegram polling;
- `worker` — обработку очереди;
- `postgres` — хранение пользователей и результатов;
- `redis` — очередь, rate limit, cache и дедупликацию.

## Локальный запуск

После запуска PostgreSQL и Redis:

```bash
.venv/bin/alembic upgrade head
.venv/bin/python -m app.main
```

В отдельном процессе:

```bash
.venv/bin/python -m app.worker
```

## Команды бота

- `/start` — главное меню;
- `/help` — инструкция;
- `/demo` — автономный демонстрационный результат;
- `/history` — история проверок пользователя;
- `/cancel` — отмена активной проверки.

Основные inline-действия: проверка материала, история, доказательства и источники,
образовательный режим и информация о проекте.

## Конфигурация провайдеров

LLM подключается через `OpenRouterLLMProvider`. Ответы с claims, поисковыми запросами,
evidence и анализом валидируются через Pydantic structured output.

Для поиска используется `YandexSearchProvider`. Результаты нормализуются, очищаются от
дубликатов, получают отдельные `quality_score` и `relevance_score`, после чего выбираются
с учётом авторитетности и разнообразия доменов.

OCR представлен заменяемым интерфейсом. В тестах и локальной демонстрации используется
`MockOCRProvider` с текстом из `MOCK_OCR_TEXT`.

## Хранение данных

Основные таблицы:

```text
User → Check → Claim → Source → Evidence → EvidenceAnalysis → Verdict
```

Доступ к истории ограничен Telegram user ID. Результаты сохраняются в PostgreSQL одной
транзакцией. Redis используется для временных данных, очереди, кэша и ограничений нагрузки.

## Безопасность

- секреты хранятся в `.env`, файл исключён из git;
- пользовательский текст и содержимое веб-страниц считаются недоверенными данными;
- prompt injection не используется как управляющая инструкция;
- URL-fetcher проверяет redirect и private/localhost адреса;
- ограничены размеры текста, изображения, число claims, запросов и источников;
- внешние HTTP-ошибки обрабатываются с bounded retry и backoff;
- недоступные и CAPTCHA-страницы не считаются доказательствами;
- категоричный verdict блокируется при недостатке usable evidence, scope mismatch или ошибке анализа;
- в Telegram показывается медицинский disclaimer;
- содержимое медицинских сообщений не выводится в обычные логи.

Перед публичным запуском необходимо отдельно проверить требования к обработке персональных
данных, срокам хранения и медицинским информационным сервисам в применимой юрисдикции.

## Проверки качества

```bash
.venv/bin/pytest
.venv/bin/ruff check .
.venv/bin/mypy app
```

Тесты покрывают извлечение claims, отрицания и контекст, URL и SSRF-защиту, OCR mock,
поиск и ranking, evidence coverage, verdict rules, prompt injection, persistence, историю,
rate limit, Redis queue, retry, dedupe, demo, cancel и образовательный режим.

## Лицензия

Лицензия проекта пока не задана.
