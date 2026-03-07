# ── Build stage ───────────────────────────────────────────────────────────────
FROM python:3.12-slim

# Prevents .pyc files and enables stdout/stderr logging immediately
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install system dependencies (needed for psycopg2 if using Postgres)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# Copy project source
COPY . .

# Collect static files at build time
RUN python manage.py collectstatic --noinput

EXPOSE 8002

# Gunicorn is the production WSGI server — don't use runserver in Docker
CMD ["gunicorn", "hospital.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3"]