# Задача 5: qwen_client — переработать промпты

**Статус:** todo  
**Зависимости:** нет (но лучше после ручной Фазы 1.5 с curl-тестами)  
**Параллельная группа:** A (можно запускать с задачами 1, 2, 4)

## Контекст

Текущие промпты рассчитаны на облачную модель `qwen-vl-plus` (~70B+). Локальная `qwen3-vl-2b-int4` в 35 раз меньше и нуждается в:
- Явной JSON-схеме с примером структуры
- Перечислениях допустимых значений
- Директиве `/no_think` для отключения thinking mode

## Что сделать

### `yaic/qwen_client.py`

Переписать `_default_prompt()` (строки 244–251):

```python
def _default_prompt(self) -> str:
    return (
        "/no_think\n"
        "Analyze this image. Return ONLY a valid JSON object, no other text, no markdown.\n\n"
        "Required schema:\n"
        "{\n"
        '  "label": "person|car|animal|package|unknown",\n'
        '  "confidence": 0.0,\n'
        '  "person": {\n'
        '    "count": 0,\n'
        '    "description": "brief description or null",\n'
        '    "details": [\n'
        '      {\n'
        '        "age_group": "child|teen|young_adult|adult|senior|unknown",\n'
        '        "gender": "male|female|unknown",\n'
        '        "appearance": "brief note",\n'
        '        "role": "courier|resident|visitor|staff|unknown"\n'
        '      }\n'
        '    ],\n'
        '    "age_summary": "e.g. 2 adults",\n'
        '    "gender_summary": "e.g. 1 male, 1 female",\n'
        '    "role_summary": "e.g. courier, unknown"\n'
        '  }\n'
        "}\n\n"
        "If no person detected, set person.count to 0 and omit other person fields.\n"
        f"Use language '{self._language}' for all free-text fields."
    )
```

Переписать `_detail_prompt()` (строки 236–241):

```python
def _detail_prompt(self) -> str:
    return (
        "/no_think\n"
        "Analyze the people in this image. Return ONLY a valid JSON object.\n\n"
        "Required schema:\n"
        "{\n"
        '  "label": "person",\n'
        '  "confidence": 0.0,\n'
        '  "person": {\n'
        '    "count": 0,\n'
        '    "description": "brief description",\n'
        '    "details": [\n'
        '      {\n'
        '        "age_group": "child|teen|young_adult|adult|senior|unknown",\n'
        '        "gender": "male|female|unknown",\n'
        '        "appearance": "brief note",\n'
        '        "role": "courier|resident|visitor|staff|unknown"\n'
        '      }\n'
        '    ],\n'
        '    "age_summary": "e.g. 2 adults",\n'
        '    "gender_summary": "e.g. 1 male, 1 female",\n'
        '    "role_summary": "e.g. courier, unknown"\n'
        '  }\n'
        "}\n\n"
        f"Use language '{self._language}' for all free-text fields."
    )
```

**Если Фаза 1.5 уже пройдена** — использовать финальный промпт, подобранный при curl-тестах, вместо предложенного выше.

## Тесты

Прямых тестов промптов нет. Запустить `poetry run pytest` — ничего не должно сломаться.

## Критерий готовности

- Оба промпта содержат `/no_think` и явную JSON-схему
- Все тесты проходят
