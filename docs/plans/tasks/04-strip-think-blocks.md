# Задача 4: qwen_client — обработка `<think>` блоков Qwen3

**Статус:** todo  
**Зависимости:** нет  
**Параллельная группа:** A (можно запускать с задачами 1, 2, 5)

## Контекст

Модели семейства Qwen3 по умолчанию генерируют `<think>...</think>` блок с рассуждениями перед ответом. Пример:

```
<think>
The image shows a person at the door. I should classify this as "person" with high confidence.
</think>
{"label": "person", "confidence": 0.85, "person": {"count": 1}}
```

Текущий парсинг (`_extract_json_object`) найдёт первый `{` — возможно, внутри `<think>` блока, а не в JSON-ответе. Это ломает парсинг.

## Что сделать

### `yaic/qwen_client.py`

Добавить `import re` (в начало файла, строка 1–9).

Добавить функцию (рядом с `_strip_json_fence`):

```python
def _strip_think_block(text: str) -> str:
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
```

В `_extract_content_json` (строка 272) — вызвать **перед** `_strip_json_fence`:

```python
text = _strip_think_block(text)
text = _strip_json_fence(text)
text = _extract_json_object(text)
```

### `tests/test_qwen_client.py`

Добавить импорт `_strip_think_block` и тесты:

```python
def test_strip_think_block_removes_thinking():
    text = '<think>some reasoning</think>\n{"label":"person"}'
    assert _strip_think_block(text) == '{"label":"person"}'

def test_strip_think_block_multiline():
    text = '<think>multi\nline\nthinking</think>{"ok":true}'
    assert _strip_think_block(text) == '{"ok":true}'

def test_strip_think_block_no_think():
    text = '{"label":"cat"}'
    assert _strip_think_block(text) == '{"label":"cat"}'
```

Также добавить интеграционный тест через `_extract_content_json`:

```python
def test_extract_content_json_with_think_block():
    client = QwenClient(api_key="key", endpoint="http://example", language="en")
    data = {
        "choices": [
            {
                "message": {
                    "content": "<think>reasoning</think>\n{\"label\":\"person\",\"confidence\":0.9}"
                }
            }
        ]
    }
    assert client._extract_content_json(data) == {"label": "person", "confidence": 0.9}
```

## Критерий готовности

- `<think>` блоки вырезаются до парсинга JSON
- Работает с многострочными `<think>` блоками
- Текст без `<think>` не меняется
- Все тесты проходят
