FROM python:3.12-slim

# uv: el gestor de paquetes del proyecto
RUN pip install --no-cache-dir uv==0.8.17

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_NO_CACHE=1

# 1) Dependencias: esta capa solo se rehace si cambian pyproject.toml o uv.lock
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

# 2) Código, web, stock y modelo entrenado
COPY src ./src
COPY web ./web
COPY stock ./stock
COPY modelos ./modelos
RUN uv sync --frozen --no-dev

# Render indica el puerto en la variable PORT; en local se usa el 8000.
ENV PATH="/app/.venv/bin:$PATH" PORT=8000

# Usuario sin privilegios: si alguien encontrara un fallo, no tendría permisos de administrador
RUN useradd -m app
USER app

CMD ["sh", "-c", "uvicorn copiloto.api:app --host 0.0.0.0 --port ${PORT}"]
