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

# Copy application source code
COPY . /app/

# Install the project only after its packages and README are present.
RUN pip install --no-cache-dir .

# Create directories for media, staticfiles, and logs
RUN mkdir -p /app/staticfiles /app/media /app/logs /app/celerybeat

EXPOSE 8000

CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--forwarded-allow-ips", "*"]
