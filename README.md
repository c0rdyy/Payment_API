# Payments API

Платежный REST API с идемпотентностью. Главная идея проекта: повторный запрос
на создание платежа с тем же `Idempotency-Key` и тем же телом должен вернуть
тот же результат, а не создать второй платеж.

Проект не списывает реальные деньги. Вместо реальный платежных провайдеров здесь
используется локальный `mock-provider`.

## Стек

- Python 3.12, FastAPI, Pydantic
- SQLAlchemy 2.0 async, Alembic
- PostgreSQL 16, Redis
- Docker, Docker Compose
- pytest, pytest-asyncio, testcontainers, Hypothesis
- ruff, mypy, pre-commit
- structlog, Prometheus, Grafana, OpenTelemetry, Jaeger

## Структура Проекта

В проекте используется Hexagonal Architecture

```text
app/
├── domain/          # Бизнес-правила
├── application/     # Сценарии и порты
│   ├── ports/       # Порты
│   └── services/    # Сервисы
├── infrastructure/  # Конкретные реализации портов
│   ├── db/          # SQLAlchemy модели, репозитории
│   ├── gateways/    # HTTPX gateway к платежному провайдеру
│   └── idempotency/ # Fingerprint тела запроса
├── api/             # FastAPI: endpoints, schemas, dependencies, middleware
└── core/            # Конфиг, логирование, метрики

mock_provider/       # Локальная заглушка платежного провайдера
alembic/             # Миграции базы данных
tests/               # Юнит-тесты, интеграционные тесты
ops/                 # Конфиг Prometheus/Grafana
```

## Базовый Сценарий Запроса

Когда клиент отправляет:

```http
POST /v1/payments
X-API-Key: dev-secret-change-me
Idempotency-Key: order-123
```

с телом:

```json
{
  "customer_id": "1e8a4d6e-4f59-4c2f-8a48-9e7d6f1d4af2",
  "amount": "199.99",
  "currency": "USD",
  "metadata": {
    "order_id": "ORD-42"
  }
}
```

происходит следующее:

1. `api/v1/payments.py` принимает HTTP-запрос.
2. `api/deps.py` проверяет `X-API-Key` и `Idempotency-Key`.
3. Для тела запроса считается fingerprint.
4. `IdempotencyService` пытается занять `Idempotency-Key`.
5. Если ключ новый, запускается `CreatePayment`.
6. `CreatePayment` создает `Money` и `Payment` из `domain`.
7. Платеж сохраняется через `PaymentRepository`.
8. `PaymentGateway` вызывает mock-provider через HTTP.
9. Mock-provider отвечает `approved` или `declined`.
10. `Payment` переводится в `succeeded` или `failed`.
11. Записываются attempt и outbox event.
12. Ответ кешируется в `idempotency_keys`.
13. API возвращает JSON клиенту.

Если отправить тот же запрос с тем же `Idempotency-Key`, API вернет старый ответ.
Если ключ тот же, но тело другое, API вернет ошибку.

## Быстрый Старт Через Docker

Требования: Docker, Docker Compose, Make

```bash
cp .env.example .env
make up
make migrate
```

`make up` собирает image и поднимает весь стек.
`make migrate` применяет Alembic-миграции к PostgreSQL.

Остановить:

```bash
make down
```

Остановить и удалить volumes с данными:

```bash
make nuke
```

## URL После Запуска

| Сервис                      | URL                           |
| --------------------------- | ----------------------------- |
| API                         | http://localhost:8000         |
| Swagger / OpenAPI           | http://localhost:8000/docs    |
| Prometheus metrics endpoint | http://localhost:8000/metrics |
| Mock-provider               | http://localhost:9000         |
| Jaeger UI                   | http://localhost:16686        |
| Prometheus                  | http://localhost:9090         |
| Grafana                     | http://localhost:3000         |

## Проверка Через Swagger

Открыть Swagger:

```text
http://localhost:8000/docs
```

Headers:

```text
X-API-Key: dev-secret-change-me
Idempotency-Key: swagger-test-1
```

Body:

```json
{
  "customer_id": "1e8a4d6e-4f59-4c2f-8a48-9e7d6f1d4af2",
  "amount": "199.99",
  "currency": "USD",
  "metadata": {
    "order_id": "ORD-42"
  }
}
```

Ожидаемый результат: `201 Created`, статус платежа `succeeded`.

Чтобы проверить идемпотентность, необходимо отправить тот же запрос еще раз с тем же
`Idempotency-Key`. Должен вернуться тот же `id` платежа.

## Локальная Разработка

Создать virtualenv и поставить зависимости:

```bash
make venv
source .venv/bin/activate
```

Если окружение уже активировано:

```bash
make install
```

Запустить быстрые тесты:

```bash
make test
```

Запустить все тесты, включая integration:

```bash
make test-all
```

## Makefile

Основные команды:

| Команда                 | Что делает                                  |
| ----------------------- | ------------------------------------------- |
| `make` / `make help`    | Показать список команд                      |
| `make venv`             | Создать `.venv` и поставить dev-зависимости |
| `make install`          | Поставить зависимости в активное окружение  |
| `make up`               | Собрать и поднять Docker stack              |
| `make down`             | Остановить stack, volumes сохранить         |
| `make logs`             | Смотреть логи API                           |
| `make migrate`          | Применить миграции внутри контейнера        |
| `make revision m="..."` | Создать новую Alembic-миграцию              |
| `make lint`             | Запустить ruff                              |
| `make fmt`              | Отформатировать код через ruff              |
| `make typecheck`        | Запустить mypy                              |
| `make test`             | Запустить тесты без integration             |
| `make test-integration` | Запустить integration-тесты                 |
| `make test-all`         | Запустить все тесты                         |
| `make check`            | `lint + typecheck + test`                   |


### Prometheus

Prometheus собирает числовые метрики:

- сколько HTTP-запросов пришло;
- сколько было ошибок;
- сколько времени занимали запросы;
- сколько платежей succeeded/failed;
- сколько было idempotency cache hits;
- сколько ошибок у gateway.

API отдает метрики на:

```text
http://localhost:8000/metrics
```

### Grafana

Grafana рисует dashboard поверх данных Prometheus.

Открыть:

```text
http://localhost:3000
```

### Jaeger

Jaeger показывает путь одного запроса.

Открыть:

```text
http://localhost:16686
```

## Тесты И Lint

Быстрый прогон:

```bash
make test
```

Полный прогон:

```bash
make test-all
```

Lint:

```bash
make lint
```