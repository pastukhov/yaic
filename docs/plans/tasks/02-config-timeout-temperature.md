# Задача 2: config — добавить inference_timeout и inference_temperature

**Статус:** todo  
**Зависимости:** нет  
**Параллельная группа:** A (можно запускать с задачами 1, 4, 5)

## Контекст

Текущий таймаут зашит в `QwenClient.__init__` как 30 сек. Локальный инференс на AX650 может занимать 10–30+ сек. Temperature не передаётся вообще, а для малой модели (2B int4) низкая temperature (0.1) критична для стабильного JSON-вывода.

Конфигурация в проекте проходит через цепочку `config.py` → `main.py` → конструкторы. Читать `os.getenv` в `qwen_client.py` нельзя — нарушает паттерн.

## Что сделать

### `yaic/config.py`

- Добавить поля в dataclass `Config` (после строки 19):
  ```python
  inference_timeout: float
  inference_temperature: float
  ```
- В `load_config()` прочитать:
  ```python
  inference_timeout = float(os.getenv("YAIC_INFERENCE_TIMEOUT", "60"))
  inference_temperature = float(os.getenv("YAIC_INFERENCE_TEMPERATURE", "0.1"))
  ```
- Передать в конструктор `Config(... inference_timeout=inference_timeout, inference_temperature=inference_temperature)`

### `yaic/main.py`

- Строки 41–46: передать новые параметры в `QwenClient`:
  ```python
  qwen = QwenClient(
      api_key=config.qwen_api_key,
      endpoint=config.qwen_endpoint,
      language=config.yaic_language,
      model=config.qwen_model,
      timeout=config.inference_timeout,
      temperature=config.inference_temperature,
  )
  ```

### `tests/test_mqtt_client.py`

- Функция `build_config()` (строки 62–75) конструирует `Config` напрямую. Добавить новые поля:
  ```python
  inference_timeout=60.0,
  inference_temperature=0.1,
  ```

## Тесты

`poetry run pytest` — все тесты должны проходить. Без обновления `build_config()` тесты **сломаются** (TypeError при создании dataclass).

## Критерий готовности

- `Config` содержит `inference_timeout` и `inference_temperature`
- Значения пробрасываются из env vars через `main.py` в `QwenClient`
- Все тесты проходят
