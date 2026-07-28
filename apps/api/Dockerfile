FROM python:3.12-slim

# POETRY_VIRTUALENVS_CREATE=false: the container *is* the environment. A nested
# venv would only add a layer to activate before every `compose exec api ...`.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_CREATE=false

RUN pip install "poetry>=2.1,<3"

WORKDIR /app

# Dependency layer: cached until pyproject/poetry.lock change, so app edits stay
# fast. Dev group included on purpose — pytest and ruff run in this container.
COPY pyproject.toml poetry.lock ./
RUN poetry install --no-cache

COPY . .

# Kept out of /app so the ./apps/api bind mount cannot shadow it.
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN sed -i 's/\r$//' /usr/local/bin/docker-entrypoint.sh \
    && chmod +x /usr/local/bin/docker-entrypoint.sh

EXPOSE 8000

# Runs `alembic upgrade head` before handing off to the CMD below.
ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
