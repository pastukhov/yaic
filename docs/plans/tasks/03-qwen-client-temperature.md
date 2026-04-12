# Задача 3: qwen_client — принять temperature и отправлять в запросе

**Статус:** todo  
**Зависимости:** Задача 2 (config передаёт temperature в конструктор)  
**Параллельная группа:** B (после группы A)

## Контекст

Текущий `_post_image()` не отправляет `temperature` в запросе — сервер использует свой дефолт (0.7). Для малой модели (2B int4) это приводит к нестабильным JSON-ответам. Нужна низкая temperature (0.1) для детерминированности.

## Что сделать

### `yaic/qwen_client.py`

- В `__init__` (строка 76): добавить параметр `temperature: float = 0.7`, сохранить в `self._temperature`
- В `_post_image()`: добавить `"temperature": self._temperature` в `base_payload` (после строки 118, внутри dict)

## Тесты

`tests/test_qwen_client.py` создаёт `QwenClient(api_key="key", endpoint="http://example", language="en")` — новый параметр имеет дефолт, поэтому существующие тесты не сломаются.

`poetry run pytest` — все тесты должны проходить.

## Критерий готовности

- `QwenClient.__init__` принимает `temperature`
- HTTP-запрос к VLM API содержит поле `"temperature"`
- Все тесты проходят
