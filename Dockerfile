FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN pip install --no-cache-dir uv

COPY pyproject.toml README.md LICENSE ./
COPY src ./src

RUN uv pip install --system .

EXPOSE 4000

CMD ["free-frontier", "--host", "0.0.0.0", "--port", "4000"]
