# Задача 6: docker-compose — обновить конфигурацию

**Статус:** todo  
**Зависимости:** Задача 2 (новые env vars `YAIC_INFERENCE_TIMEOUT`, `YAIC_INFERENCE_TEMPERATURE`)  
**Параллельная группа:** B (после группы A)

## Контекст

Текущий `docker-compose.yaml` имеет проблемы:
- Дефолты указывают на DashScope (облачный API)
- Отсутствуют `MQTT_TOPIC_STATUS` и `MQTT_TOPIC_LOG`, которые обязательны в `config.py`
- Нет новых env vars для таймаута и temperature

## Что сделать

### `docker-compose.yaml`

Заменить секцию `environment` сервиса `yaic` (строки 15–24):

```yaml
    environment:
      MQTT_HOST: ${MQTT_HOST:-mqtt}
      MQTT_PORT: ${MQTT_PORT:-1883}
      MQTT_TOPIC_IN: ${MQTT_TOPIC_IN:-yaic/input/+/image}
      MQTT_TOPIC_OUT: ${MQTT_TOPIC_OUT:-yaic/output}
      MQTT_TOPIC_STATUS: ${MQTT_TOPIC_STATUS:-yaic/status}
      MQTT_TOPIC_LOG: ${MQTT_TOPIC_LOG:-yaic/log}
      QWEN_API_KEY: ${QWEN_API_KEY:-none}
      QWEN_ENDPOINT: ${QWEN_ENDPOINT:-http://192.168.11.128:8000/v1/chat/completions}
      QWEN_MODEL: ${QWEN_MODEL:-qwen3-vl-2b-int4-ax650}
      YAIC_LANGUAGE: ${YAIC_LANGUAGE:-ru}
      YAIC_INFERENCE_TIMEOUT: ${YAIC_INFERENCE_TIMEOUT:-60}
      YAIC_INFERENCE_TEMPERATURE: ${YAIC_INFERENCE_TEMPERATURE:-0.1}
      LOG_LEVEL: ${LOG_LEVEL:-INFO}
```

Ключевые изменения:
- `MQTT_TOPIC_STATUS` и `MQTT_TOPIC_LOG` — добавлены (без них `config.py` падает)
- `MQTT_TOPIC_IN` — дефолт `yaic/input/+/image` вместо `yaic/in` (соответствует реальной подписке)
- `QWEN_API_KEY` — дефолт `none` вместо обязательного
- `QWEN_ENDPOINT` — Pyramid вместо DashScope, **полный URL включая `/v1/chat/completions`**
- `QWEN_MODEL` — модель Pyramid
- `YAIC_INFERENCE_TIMEOUT`, `YAIC_INFERENCE_TEMPERATURE` — новые

## Тесты

Нет автоматических тестов docker-compose. Проверить:
```bash
docker compose config  # валидация YAML
```

## Критерий готовности

- `docker compose config` проходит без ошибок
- Все обязательные env vars из `config.py` присутствуют с дефолтами
- Дефолты указывают на Pyramid, а не DashScope
