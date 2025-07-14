# Prometheus Metrics для FastAPI приложения

## Обзор

Приложение настроено для сбора детальных метрик через Prometheus. Метрики доступны на эндпоинте `/metrics`.

## Доступные метрики

### Стандартные метрики (автоматически собираются)

- `fastapi_requests_total` - общее количество запросов
- `fastapi_request_duration_seconds` - время выполнения запросов
- `fastapi_requests_inprogress` - количество активных запросов
- `fastapi_request_size_bytes` - размер входящих запросов
- `fastapi_response_size_bytes` - размер исходящих ответов
- `fastapi_exceptions_total` - количество исключений

### Кастомные метрики основного приложения

#### `http_requests_total`
Общее количество HTTP запросов с детализацией:
- `method` - HTTP метод (GET, POST, etc.)
- `endpoint` - путь эндпоинта
- `status` - HTTP статус код
- `event_name` - имя события (определяется по домену)

#### `http_request_duration_seconds`
Время выполнения HTTP запросов:
- `method` - HTTP метод
- `endpoint` - путь эндпоинта
- `event_name` - имя события

#### `http_requests_active`
Количество активных HTTP запросов:
- `event_name` - имя события

#### `http_errors_total`
Количество HTTP ошибок:
- `method` - HTTP метод
- `endpoint` - путь эндпоинта
- `error_type` - тип ошибки
- `event_name` - имя события

### Метрики админки

#### `admin_requests_total`
Количество запросов к админке:
- `method` - HTTP метод
- `endpoint` - путь эндпоинта
- `status` - HTTP статус код
- `admin_section` - секция админки (auth, database, users, settings, logs, other)

#### `admin_request_duration_seconds`
Время выполнения запросов к админке:
- `method` - HTTP метод
- `endpoint` - путь эндпоинта
- `admin_section` - секция админки

#### `admin_requests_active`
Количество активных запросов к админке:
- `admin_section` - секция админки

#### `admin_errors_total`
Количество ошибок в админке:
- `method` - HTTP метод
- `endpoint` - путь эндпоинта
- `error_type` - тип ошибки
- `admin_section` - секция админки

#### `admin_login_attempts_total`
Количество попыток входа в админку:
- `status` - успех (success) или неудача (failed)
- `ip_address` - IP адрес пользователя

#### `admin_session_duration_seconds`
Длительность сессий в админке:
- `admin_section` - секция админки

## Настройка

### Переменные окружения

- `ENABLE_METRICS=true` - включить/выключить сбор метрик

### Исключенные эндпоинты

Следующие эндпоинты исключены из сбора метрик:
- `/metrics` - сам эндпоинт метрик
- `/static` - статические файлы

**Примечание:** Админка (`/admin/*`) теперь имеет отдельные метрики и не исключена из мониторинга.

## Примеры запросов к метрикам

### Получить все метрики
```bash
curl http://localhost:8000/metrics
```

### Получить только кастомные метрики
```bash
curl http://localhost:8000/metrics | grep "http_"
```

### Получить метрики админки
```bash
curl http://localhost:8000/metrics | grep "admin_"
```

### Примеры PromQL запросов

#### Количество запросов в минуту по эндпоинтам
```promql
rate(http_requests_total[1m])
```

#### Среднее время ответа по эндпоинтам
```promql
rate(http_request_duration_seconds_sum[5m]) / rate(http_request_duration_seconds_count[5m])
```

#### Количество ошибок по типам
```promql
rate(http_errors_total[5m])
```

#### Активные запросы по событиям
```promql
http_requests_active
```

#### Метрики админки

##### Количество запросов к админке по секциям
```promql
rate(admin_requests_total[5m]) by (admin_section)
```

##### Время ответа админки по секциям
```promql
rate(admin_request_duration_seconds_sum[5m]) by (admin_section) / rate(admin_request_duration_seconds_count[5m]) by (admin_section)
```

##### Попытки входа в админку
```promql
rate(admin_login_attempts_total[5m]) by (status, ip_address)
```

##### Неудачные попытки входа (для алертов)
```promql
rate(admin_login_attempts_total{status="failed"}[5m]) by (ip_address)
```

## Мониторинг в Grafana

### Рекомендуемые дашборды

1. **Общий обзор приложения**
   - Количество запросов в секунду
   - Время ответа
   - Количество ошибок
   - Активные запросы

2. **Мониторинг по событиям**
   - Метрики сгруппированные по `event_name`
   - Сравнение производительности между событиями

3. **Мониторинг эндпоинтов**
   - Топ медленных эндпоинтов
   - Топ эндпоинтов с ошибками
   - Использование по HTTP методам

4. **Мониторинг админки**
   - Активность по секциям админки
   - Попытки входа (успешные/неудачные)
   - Время ответа админки
   - Подозрительная активность (много неудачных попыток входа)

### Алерты

Рекомендуемые алерты:
- Время ответа > 2 секунд
- Количество ошибок > 5% от общего числа запросов
- Количество активных запросов > 100
- **Админка:** Более 5 неудачных попыток входа с одного IP за 5 минут
- **Админка:** Время ответа админки > 5 секунд

## Интеграция с Prometheus

Добавьте в `prometheus.yml`:

```yaml
scrape_configs:
  - job_name: 'fastapi-app'
    static_configs:
      - targets: ['localhost:8000']
    metrics_path: '/metrics'
    scrape_interval: 15s
``` 