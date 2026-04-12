# Задача 1: config — сделать QWEN_API_KEY необязательным

**Статус:** todo  
**Зависимости:** нет  
**Параллельная группа:** A (можно запускать с задачами 2, 4, 5)

## Контекст

Для локального инференса на M5Stack AI Pyramid API key не нужен — аутентификация в ModuleLLM-OpenAI-Plugin закомментирована. Но `config.py` требует `QWEN_API_KEY` как обязательную переменную и падает при её отсутствии.

## Что сделать

### `yaic/config.py`

- Строка 29: заменить `qwen_api_key = os.getenv("QWEN_API_KEY")` на `qwen_api_key = os.getenv("QWEN_API_KEY", "none")`
- Строки 46–47: убрать блок:
  ```python
  if not qwen_api_key:
      missing.append("QWEN_API_KEY")
  ```

## Тесты

Прямых тестов `config.py` нет. Запустить `poetry run pytest` — ничего не должно сломаться.

## Критерий готовности

- YAIC запускается без переменной `QWEN_API_KEY` в окружении
- `config.qwen_api_key` при этом равен `"none"`
- Все тесты проходят
