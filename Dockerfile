FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir poetry

COPY pyproject.toml /app/pyproject.toml
COPY yaic /app/yaic

RUN poetry config virtualenvs.create false \
  && poetry install --no-interaction --no-ansi --only main --no-root

ENV PYTHONUNBUFFERED=1

CMD ["python", "-m", "yaic"]
