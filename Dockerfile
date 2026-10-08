FROM python:3.12-slim

# Prevent Python from writing .pyc files and enable unbuffered output
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install dependencies in a separate layer so source/template changes reuse it.
COPY pyproject.toml /tmp/dependencies/pyproject.toml
RUN python -c 'import pathlib, tomllib; p = tomllib.loads(pathlib.Path("/tmp/dependencies/pyproject.toml").read_text()); pathlib.Path("/tmp/dependencies/requirements.txt").write_text("\n".join(p["build-system"]["requires"] + ["wheel"] + p["project"]["dependencies"]) + "\n")' \
    && pip install --no-cache-dir -r /tmp/dependencies/requirements.txt

# Install the application after its packages and README are present.
COPY . /app/
RUN pip install --no-cache-dir --no-deps --no-build-isolation .

# Create directories for media, staticfiles, and logs
RUN mkdir -p /app/staticfiles /app/media /app/logs /app/celerybeat

EXPOSE 8000

CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--forwarded-allow-ips", "*"]
