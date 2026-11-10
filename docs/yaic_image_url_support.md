# YAIC: поддержка image_url и image_b64

## Контекст

YAIC должен поддерживать два способа передачи изображения через MQTT:

| Поле | Источник | Когда использовать |
|------|----------|--------------------|
| `image_b64` | Base64-encoded bytes | Любой клиент с прямым доступом к файлу |
| `image_url` | HTTP(S) URL | Home Assistant и другие системы без прямого доступа к файлу |

Оба формата работают одновременно — YAIC определяет тип по наличию поля.

---

## Формат MQTT-сообщения

**Вариант 1 — image_b64:**
```json
{
  "image_b64": "<base64-encoded JPEG>",
  "device": "domofon"
}
```

**Вариант 2 — image_url:**
```json
{
  "image_url": "http://homeassistant.local:8123/local/domofon_latest.jpg",
  "device": "domofon"
}
```

Поле `device` обязательно в обоих случаях.

---

## Доработка YAIC

### 1. Pydantic-схема входящего сообщения

```python
from pydantic import BaseModel, model_validator
from typing import Optional

class ImageMessage(BaseModel):
    device: str
    image_b64: Optional[str] = None
    image_url: Optional[str] = None

    @model_validator(mode="after")
    def check_image_source(self) -> "ImageMessage":
        if not self.image_b64 and not self.image_url:
            raise ValueError("Payload must contain 'image_b64' or 'image_url'")
        return self
```

### 2. Универсальный загрузчик изображения

```python
import base64
import httpx
from typing import Optional

async def fetch_image_bytes(
    msg: ImageMessage,
    http_headers: Optional[dict] = None,
    timeout: float = 5.0,
) -> bytes:
    """
    Возвращает сырые байты изображения из image_b64 или image_url.
    image_b64 имеет приоритет если переданы оба поля.
    """
    if msg.image_b64:
        return base64.b64decode(msg.image_b64)

    async with httpx.AsyncClient() as client:
        response = await client.get(
            msg.image_url,
            headers=http_headers or {},
            timeout=timeout,
            follow_redirects=True,
        )
        response.raise_for_status()
        return response.content
```

### 3. Конфигурация HTTP-заголовков

Для доступа к защищённым источникам (HA требует токен):

```python
import os

HA_TOKEN = os.getenv("HA_TOKEN", "")

def get_http_headers_for_url(url: str) -> dict:
    """Подбирает нужные заголовки в зависимости от хоста."""
    if HA_TOKEN and (":8123" in url or "homeassistant" in url):
        return {"Authorization": f"Bearer {HA_TOKEN}"}
    return {}
```

Использование:

```python
headers = get_http_headers_for_url(msg.image_url or "")
image_bytes = await fetch_image_bytes(msg, http_headers=headers)
```

### 4. Обработчик MQTT-топика

```python
import json

async def on_image_message(topic: str, raw_payload: str) -> None:
    try:
        data = json.loads(raw_payload)
        msg = ImageMessage(**data)
    except Exception as e:
        logger.error(f"Invalid image message on {topic}: {e}")
        return

    try:
        image_bytes = await fetch_image_bytes(
            msg,
            http_headers=get_http_headers_for_url(msg.image_url or ""),
        )
    except Exception as e:
        logger.error(f"Failed to fetch image for device {msg.device}: {e}")
        return

    result = await classify_image(image_bytes, source=msg.device)

    await mqtt_publish(
        topic=f"yaic/output/{msg.device}/classification",
        payload=json.dumps({
            "label": result.label,
            "confidence": result.confidence,
            "device": msg.device,
        }),
    )
```

---

## Long-lived token для Home Assistant

1. В HA: **Profile → Long-lived access tokens → Create token**
2. Добавить в `.env` YAIC:
   ```
   HA_TOKEN=eyJ0eXAiOiJKV1QiLCJhbGc...
   ```
3. При локальном развёртывании на том же хосте URL будет:
   `http://localhost:8123/local/<filename>`

---

## Обновление Blueprint

Добавить input `ha_base_url` и использовать вместо `readfile`:

```yaml
  input:
    ha_base_url:
      name: Home Assistant Base URL
      description: Базовый URL HA для формирования image_url (только для image_url режима).
      default: "http://localhost:8123"
      selector:
        text: {}

  # ...

  variables:
    _ha_base_url: !input ha_base_url

  # В action вместо readfile:
  - action: mqtt.publish
    data:
      topic: '{{ _mqtt_base.rstrip("/") ~ "/" ~ _source_id ~ "/image" }}'
      payload: >-
        {{ {
          "image_url": _ha_base_url.rstrip("/") ~ "/local/" ~ _snapshot_path[13:],
          "device": _source_id
        } | tojson }}
```

> `_snapshot_path[13:]` срезает `/config/www/` — остаётся путь для `/local/`.

---

## Итоговый поток

```
Клиент A (Home Assistant)          Клиент B (любой другой)
        │                                   │
        │  {"image_url": "http://..."}      │  {"image_b64": "..."}
        ▼                                   ▼
          MQTT: yaic/input/<device>/image
                        │
                        ▼
                ImageMessage (pydantic)
                        │
              ┌─────────┴──────────┐
              │                    │
         image_b64            image_url
         base64.decode()      httpx.get()
              │                    │
              └─────────┬──────────┘
                        │
                   image bytes
                        │
                        ▼
                classify_image()
                        │
                        ▼
        MQTT: yaic/output/<device>/classification
          {"label": "person", "confidence": 0.97}
```
