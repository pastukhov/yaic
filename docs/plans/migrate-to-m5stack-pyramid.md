# Миграция YAIC на M5Stack AI Pyramid

**Дата:** 2026-04-12  
**Статус:** Draft

---

## Контекст

YAIC сейчас использует облачный Qwen VL API через Alibaba DashScope:
- Эндпоинт: `https://dashscope-intl.aliyuncs.com/compatible-mode/v1/chat/completions`
- Модель: `qwen-vl-plus`
- Формат: OpenAI-compatible (multimodal, изображение + текст → JSON)

M5Stack AI Pyramid — локальное устройство с чипом AX650, 4 ГБ RAM. Цель: полностью убрать зависимость от внешнего API, перейти на локальный инференс.

---

## Выбор модели

### Требования к модели

YAIC отправляет изображение + текстовый промпт и ожидает структурированный JSON:
```json
{
  "label": "person",
  "confidence": 0.92,
  "person": {
    "count": 2,
    "description": "...",
    "details": [{"age_group": "adult", "gender": "male", "appearance": "...", "role": "..."}],
    "age_summary": "2 adults",
    "gender_summary": "2 male",
    "role_summary": "unknown"
  }
}
```

Модель **обязана** поддерживать vision (multimodal) — принимать изображение в промпте.

### Кандидаты (только VLM-модели из списка)

| Модель | Параметры | Квантование | Разрешение | Оценка |
|--------|-----------|-------------|------------|--------|
| `smolvlm-256m-ax650` | 256M | — | 256px | Слишком мала для структурного JSON |
| `internvl2.5-1b-448-ax650` | 1B | — | 448px | Старая версия, хуже InternVL3 |
| `internvl3-1b-448-ax650` | 1B | — | 448px | Хорошая, но 1B может не справляться со сложным JSON |
| **`qwen3-vl-2b-int4-ax650`** | **2B** | **int4** | — | **Лучший выбор** |

### Обоснование выбора: `qwen3-vl-2b-int4-ax650`

1. **Та же семья моделей** — текущий `qwen-vl-plus` тоже от Qwen VL, промпты совместимы
2. **2B параметров** против 1B у InternVL: лучше справляется со structured JSON output и person analytics
3. **int4 квантование**: ~1 ГБ RAM, хорошо укладывается в 4 ГБ устройства
4. **Оптимизирован для AX650** — нативная поддержка чипа

**Резервный вариант**: `internvl3-1b-448-ax650` — если `qwen3-vl-2b-int4` не будет уверенно выдавать структурированный JSON.

---

## Архитектура HTTP API M5Stack AI Pyramid

Источник: репозиторий [m5stack/ModuleLLM-OpenAI-Plugin](https://github.com/m5stack/ModuleLLM-OpenAI-Plugin) и [m5stack/StackFlow](https://github.com/m5stack/StackFlow).

### Стек

```
YAIC (HTTP-клиент)
    ↓  POST /v1/chat/completions  port 8000
ModuleLLM-OpenAI-Plugin (FastAPI, Python)
    ↓  ZMQ TCP  port 10001
StackFlow (C++, main_vlm / main_llm)
    ↓
AX650 NPU
```

### HTTP эндпоинты (порт 8000)

| Метод | Путь | Назначение |
|-------|------|------------|
| POST | `/v1/chat/completions` | Чат / multimodal инференс |
| POST | `/v1/completions` | Текстовый инференс |
| GET | `/v1/models` | Список доступных моделей |
| POST | `/v1/audio/speech` | TTS |
| POST | `/v1/audio/transcriptions` | ASR |

### Формат запроса (chat completions)

Стандартный OpenAI-формат, полностью совместим с тем, что уже отправляет YAIC:

```json
{
  "model": "<model-name-from-config>",
  "messages": [
    {
      "role": "user",
      "content": [
        {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,..."}},
        {"type": "text", "text": "...prompt..."}
      ]
    }
  ],
  "temperature": 0.7,
  "max_tokens": 1000,
  "stream": false
}
```

**Изображения**: принимаются именно в формате `data:image/...;base64,...` в поле `image_url.url` — это точно то, что YAIC уже отправляет. Также поддерживаются внешние URL (плагин скачивает их сам, до 4 МБ).

### Аутентификация

Заголовок `Authorization: Bearer <key>` — **обязателен по форме**, но валидация в текущем коде закомментирована. Любая строка подойдёт.

### `response_format`

В коде плагина нет явной обработки `response_format: json_object` — параметр передаётся в конфиг StackFlow, но без специальной логики. **Вероятно, будет проигнорирован** (не вернёт 400). Существующий fallback в `qwen_client.py` (строки 139–148) останется как страховка.

### Конфигурация моделей на устройстве

Модели описываются в `/opt/m5stack/bin/ModuleLLM-OpenAI-Plugin/config/config.yaml`:

```yaml
server:
  host: 127.0.0.1
  port: 10001   # ZMQ-порт StackFlow

models:
  qwen3-vl-2b:          # <-- это имя модели в API-запросах
    type: vlm           # или vision_model
    model_name: qwen3-vl-2b-int4-ax650  # имя пакета на устройстве
```

Имя из ключа `models:` — это то, что нужно передавать в поле `model` запроса.  
**Точный формат ключей нужно проверить на устройстве** через `GET /v1/models`.

### Важное: типы бэкендов для VLM

Диспетчер плагина маппит тип модели → бэкенд:
- `"vlm"` → `LlmClientBackend` (ZMQ к StackFlow, но парсит только текст из messages)
- `"vision_model"` → `VisionModelBackend` (AsyncOpenAI → другой OpenAI-эндпоинт, полноценная обработка изображений)

Для YAIC нужен тип **`vision_model`**, чтобы изображения реально передавались в модель.

---

## Необходимые изменения в коде

### Важно: формат `QWEN_ENDPOINT`

**QWEN_ENDPOINT — это полный URL** включая путь `/chat/completions`. Текущий код `qwen_client.py:133` делает `requests.post(self._endpoint, ...)` без добавления пути. Текущее значение по умолчанию в docker-compose.yaml (строка 21):
```
https://dashscope-intl.aliyuncs.com/compatible-mode/v1/chat/completions
```

Для Pyramid правильное значение:
```
http://192.168.11.128:8000/v1/chat/completions
```

Указание `http://192.168.11.128:8000/v1` **приведёт к 404**.

### Шаг 1: Установка модели на устройство

```bash
# Через M5Stack пакетный менеджер (уточнить по документации)
m5stack install llm-model-qwen3-vl-2b-int4-ax650
```

После установки — проверить, что модель появилась:
```bash
curl http://192.168.11.128:8000/v1/models
```

### Шаг 2: Изменения в `config.py` и `main.py`

**2a.** Сделать `QWEN_API_KEY` необязательным (для локального инференса ключ не нужен):

```python
# config.py
qwen_api_key = os.getenv("QWEN_API_KEY", "none")
# убрать "QWEN_API_KEY" из списка missing
```

**2b.** Добавить настраиваемый таймаут. Поле `timeout` нужно провести через всю цепочку:
- Добавить `inference_timeout: float` в `Config` (dataclass)
- Прочитать из `os.getenv("YAIC_INFERENCE_TIMEOUT", "60")` в `load_config()`
- Передать в `QwenClient(... timeout=config.inference_timeout)` в `main.py`

**Не читать os.getenv в qwen_client.py** — это нарушит текущий паттерн конфигурации и тесты.

**2c.** Добавить настраиваемую `temperature`:
- Добавить `inference_temperature: float` в `Config`
- Прочитать из `os.getenv("YAIC_INFERENCE_TEMPERATURE", "0.1")`
- Передать в `QwenClient`
- Использовать в `_post_image()` в `base_payload`

Низкая temperature (0.1) критична для малой модели — снижает рандомность JSON-ответов.

**Влияние на тесты**: `build_config()` в `test_mqtt_client.py` конструирует `Config` напрямую — при добавлении полей в dataclass этот тест сломается. Нужно обновить.

### Шаг 3: Изменения в `qwen_client.py`

#### 3a. Принять `temperature` в конструкторе

Добавить параметр `temperature: float = 0.7` в `__init__`, хранить в `self._temperature`.
В `_post_image()` добавить `"temperature": self._temperature` в `base_payload`.

#### 3b. Обработка `<think>` блоков Qwen3

Qwen3 по умолчанию генерирует `<think>...</think>` перед ответом. Это ломает JSON-парсинг, потому что `_extract_json_object` найдёт `{` внутри `<think>` блока.

Добавить в `_extract_content_json` (перед вызовом `_strip_json_fence`):
```python
text = _strip_think_block(text)
```

Новая функция:
```python
import re

def _strip_think_block(text: str) -> str:
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
```

Добавить тест: вход `"<think>reasoning here</think>\n{\"label\":\"person\"}"` → `{"label":"person"}`.

#### 3c. `response_format`

Оставить как есть — fallback уже работает. Если Pyramid проигнорирует параметр (не вернёт 400), запрос пройдёт нормально. Если вернёт 400, fallback повторит без него.

#### 3d. Двойной запрос

Оставить как есть на первом этапе. На этапе оптимизации — объединить в один промпт.

### Шаг 4: Переработка промптов (обязательно)

`qwen-vl-plus` — облачная модель ~70B+. Локальная `qwen3-vl-2b-int4` в 35 раз меньше. Текущие промпты слишком лаконичны.

#### Текущий `_default_prompt()` — проблемы:
- Нет примера JSON-структуры → модель может придумать свою
- Нотация `details[age_group, ...]` неоднозначна
- Нет допустимых значений для перечислимых полей
- Qwen3 запускает режим мышления (`<think>...</think>`) по умолчанию

#### Новый `_default_prompt()`:

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

Ключевые изменения:
- **`/no_think`** в начале — отключает thinking mode у Qwen3 (запасной вариант: если `/no_think` не работает, использовать system message `"You must not use thinking mode."`)
- **Явная JSON-схема с примером** — модель точно знает структуру
- **Перечисления допустимых значений** — снижает галлюцинации

#### `_detail_prompt()` — аналогично улучшить, добавить `/no_think` и JSON-схему.

### Шаг 5: `docker-compose.yaml`

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

Также исправить: в текущем docker-compose.yaml отсутствуют `MQTT_TOPIC_STATUS` и `MQTT_TOPIC_LOG`, которые обязательны в `config.py`.

---

## План действий

### Фаза 1 — Разведка устройства (ручная)

- [ ] Установить модель `qwen3-vl-2b-int4-ax650` на устройство (IP: 192.168.11.128)
- [ ] Проверить доступность API: `curl http://192.168.11.128:8000/v1/models`
- [ ] Узнать точное имя модели (ключ из `config.yaml` или из `/v1/models`)
- [ ] Убедиться, что тип модели в конфиге — `vision_model` (не `vlm`)

### Фаза 1.5 — Тест промптов через curl (ручная, до правки кода)

```bash
# 1. Сгенерировать base64 тестового изображения
B64=$(base64 -w0 /path/to/test.jpg)

# 2. Итеративно тестировать промпты
curl -s http://192.168.11.128:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer none" \
  -d "{
    \"model\": \"<MODEL_NAME>\",
    \"messages\": [{
      \"role\": \"user\",
      \"content\": [
        {\"type\": \"image_url\", \"image_url\": {\"url\": \"data:image/jpeg;base64,$B64\"}},
        {\"type\": \"text\", \"text\": \"/no_think\nReturn JSON with label and confidence only.\"}
      ]
    }],
    \"temperature\": 0.1,
    \"max_tokens\": 500
  }"
```

- [ ] Добиться стабильного JSON-ответа (5/5 попыток с одним изображением)
- [ ] Замерить время ответа
- [ ] Проверить, работает ли `/no_think` (нет `<think>` блоков в ответе)
- [ ] Зафиксировать финальный промпт

### Фаза 2 — Изменения кода (задачи для subagent-driven development)

См. раздел «Задачи для SDD» ниже.

### Фаза 3 — Оптимизация (после подтверждения базовой работы)

- [ ] Объединить `_default_prompt()` + `_detail_prompt()` в один запрос
- [ ] Замерить полную задержку от MQTT-события до публикации результата
- [ ] При необходимости — попробовать `internvl3-1b-448-ax650` как альтернативу

### Фаза 4 — Финализация

- [ ] Обновить `README.md` (новые env vars, убрать упоминание DashScope)
- [ ] Обновить `docker-compose.yaml` для прода
- [ ] Перезапустить systemd-сервис: `systemctl restart yaic-compose`

---

## Задачи для subagent-driven development (Фаза 2)

Задачи ниже — независимые единицы работы, каждая самодостаточна и может выполняться параллельно (кроме явных зависимостей). Каждая задача включает правку кода **и** обновление тестов.

### Задача 1: config — сделать QWEN_API_KEY необязательным

**Файлы:** `yaic/config.py`  
**Что сделать:**
- Установить `qwen_api_key = os.getenv("QWEN_API_KEY", "none")` (строка 29)
- Убрать блок `if not qwen_api_key: missing.append(...)` (строки 46–47)
- Тесты: не затронуты (нет тестов config.py)

### Задача 2: config — добавить inference_timeout и inference_temperature

**Файлы:** `yaic/config.py`, `yaic/main.py`, `tests/test_mqtt_client.py`  
**Что сделать:**
- Добавить поля `inference_timeout: float` и `inference_temperature: float` в dataclass `Config` (после строки 19)
- В `load_config()` прочитать из env: `float(os.getenv("YAIC_INFERENCE_TIMEOUT", "60"))` и `float(os.getenv("YAIC_INFERENCE_TEMPERATURE", "0.1"))`
- В `main.py:41–46` передать `timeout=config.inference_timeout` и `temperature=config.inference_temperature` в конструктор `QwenClient`
- В `tests/test_mqtt_client.py:62–75` добавить новые поля в `build_config()` (иначе тест сломается при создании `Config`)

### Задача 3: qwen_client — принять temperature и отправлять в запросе

**Файлы:** `yaic/qwen_client.py`  
**Зависит от:** Задача 2 (чтобы temperature передавалась из config)  
**Что сделать:**
- Добавить параметр `temperature: float = 0.7` в `__init__` (строка 76), сохранить в `self._temperature`
- В `_post_image()` добавить `"temperature": self._temperature` в `base_payload` (после строки 118)
- Тесты: обновить создание `QwenClient` в `test_qwen_client.py` если нужно

### Задача 4: qwen_client — обработка `<think>` блоков Qwen3

**Файлы:** `yaic/qwen_client.py`, `tests/test_qwen_client.py`  
**Что сделать:**
- Добавить функцию `_strip_think_block(text: str) -> str` — удаляет `<think>...</think>` через `re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()`
- Вызвать её в `_extract_content_json` **перед** `_strip_json_fence` (перед строкой 272)
- Добавить тесты:
  - `<think>some reasoning</think>\n{"label":"person"}` → `{"label":"person"}`
  - `<think>multi\nline\nthinking</think>{"ok":true}` → `{"ok":true}`
  - Текст без `<think>` — не меняется

### Задача 5: qwen_client — переработать промпты

**Файлы:** `yaic/qwen_client.py`  
**Зависит от:** Результатов Фазы 1.5 (финальный промпт). Если Фаза 1.5 ещё не пройдена — использовать промпт из этого плана как начальный вариант.  
**Что сделать:**
- Переписать `_default_prompt()` (строки 244–251): добавить `/no_think`, JSON-схему с перечислениями допустимых значений, явный пример структуры
- Переписать `_detail_prompt()` (строки 236–241): аналогично — `/no_think`, JSON-схему
- Тесты: нет прямых тестов промптов; убедиться, что `poetry run pytest` проходит

### Задача 6: docker-compose — обновить конфигурацию

**Файлы:** `docker-compose.yaml`  
**Что сделать:**
- Добавить недостающие `MQTT_TOPIC_STATUS` и `MQTT_TOPIC_LOG` (сейчас отсутствуют, но обязательны в config.py)
- Изменить дефолт `QWEN_ENDPOINT` на `http://192.168.11.128:8000/v1/chat/completions`
- Изменить дефолт `QWEN_MODEL` на имя модели Pyramid
- Добавить `YAIC_INFERENCE_TIMEOUT` и `YAIC_INFERENCE_TEMPERATURE`
- Сделать `QWEN_API_KEY` с дефолтом `none`

### Граф зависимостей

```
Задача 1 (api key)     ─── независимая
Задача 2 (config)      ─── независимая
Задача 3 (temperature) ─── зависит от Задачи 2
Задача 4 (<think>)     ─── независимая
Задача 5 (промпты)     ─── независимая (но лучше после Фазы 1.5)
Задача 6 (compose)     ─── зависит от Задачи 2 (новые env vars)
```

Параллельно можно запускать: 1 + 2 + 4 + 5, затем 3 + 6.

---

## Риски

| Риск | Вероятность | Митигация |
|------|-------------|-----------|
| Модель в конфиге как `vlm` вместо `vision_model` — изображения не передаются | Высокая | Проверить `/v1/models` и `config.yaml` на устройстве, исправить тип |
| Qwen3 выдаёт `<think>` блоки, ломающие JSON-парсинг | Высокая | `/no_think` в промпте + `_strip_think_block()` как страховка (Задача 4) |
| Модель не выдаёт надёжный JSON даже с хорошим промптом | Средняя | Добавить few-shot пример в промпт; попробовать `internvl3-1b` |
| Инференс >60 сек | Низкая | Увеличить `YAIC_INFERENCE_TIMEOUT`; объединить два запроса в один |
| 2B int4 теряет точность в person analytics | Низкая | Резервный вариант: `internvl3-1b-448-ax650` |

---

## Что остаётся без изменений

- `processor.py` — вся оркестрация не меняется
- `mqtt_client.py` — MQTT логика не меняется
- `ha_discovery.py` — интеграция с Home Assistant не меняется
- Структура `ClassificationResult` / `PersonSummary` / `PersonDetail` — не меняется

---

## Источники

- [m5stack/ModuleLLM-OpenAI-Plugin](https://github.com/m5stack/ModuleLLM-OpenAI-Plugin) — FastAPI сервер, порт 8000, OpenAI-совместимые эндпоинты
- [m5stack/StackFlow](https://github.com/m5stack/StackFlow) — ZMQ-бэкенд, порт 10001, C++ VLM runtime
