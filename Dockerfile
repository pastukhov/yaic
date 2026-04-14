FROM python:3.11-slim

WORKDIR /app

# OS packages required by InsightFace / OpenCV
RUN apt-get update && apt-get install -y --no-install-recommends \
  libgl1 \
  libglib2.0-0 \
  libgomp1 \
  g++ \
  cmake \
  && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir poetry

COPY pyproject.toml /app/pyproject.toml
COPY yaic /app/yaic

RUN poetry config virtualenvs.create false \
  && poetry install --no-interaction --no-ansi --only main --no-root

# Pre-download InsightFace buffalo_l model so the container starts cold-start-free
RUN python -c "\
  import insightface.app as isf_app; \
  a = isf_app.FaceAnalysis(name='buffalo_l', providers=['CPUExecutionProvider']); \
  a.prepare(ctx_id=-1)"

ENV PYTHONUNBUFFERED=1

CMD ["python", "-m", "yaic"]
