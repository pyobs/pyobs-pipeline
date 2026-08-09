FROM python:3.12-slim
WORKDIR /app

# git is needed at build time -- pyobs-core is pinned to a git rev (see pyproject.toml),
# not a PyPI release, until the Night->Reduction rename ships in one.
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY . .

CMD ["uv", "run", "gunicorn", "pyobs_pipeline.wsgi:application", "--bind", "0.0.0.0:8000"]
