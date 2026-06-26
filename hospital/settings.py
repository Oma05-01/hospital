"""
Django settings for hospital project — Docker/production ready.
"""

import os
from datetime import timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# ── Security ──────────────────────────────────────────────────────────────────
# Read from environment — never hardcode in production
SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY', '7k#Br9!mL2pQ*wZ ')
JWT_ALGORITHM = 'HS256'

DEBUG = os.environ.get('DJANGO_DEBUG', 'False') == 'True'

raw_allowed_hosts = os.environ.get('ALLOWED_HOSTS', '')

# 1. Start with our guaranteed local development defaults
ALLOWED_HOSTS = ['localhost', '127.0.0.1', 'localhost:8000 ', '127.0.0.1:8000']

# 2. Safely add any external hosts from your environment if they exist
if raw_allowed_hosts:
    # Split by spaces or commas just in case
    for host in raw_allowed_hosts.replace(',', ' ').split():
        cleaned_host = host.strip("'\" ")
        if cleaned_host and cleaned_host not in ALLOWED_HOSTS:
            ALLOWED_HOSTS.append(cleaned_host)

print("--- CURRENT ALLOWED_HOSTS LIST:", ALLOWED_HOSTS)

CSRF_TRUSTED_ORIGINS = os.environ.get(
    'CSRF_TRUSTED_ORIGINS',
    'http://localhost:8000 http://127.0.0.1:8000'
).split()

# ── Apps ──────────────────────────────────────────────────────────────────────
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'corsheaders',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'patients',
    'appointments',
    'records',
    'staff',
    'rest_framework',
    'rest_framework.authtoken',
    'django_extensions',
    'rest_framework_simplejwt',
    'drf_spectacular',
]

# ── Middleware ────────────────────────────────────────────────────────────────
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',        # serve static files in Docker
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'staff.custom_middleware.StaffOnlyMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'patients.custom_middleware.PatientOnlyMiddleware',
    'staff.custom_middleware.DebugToolbarExcludeAPIMiddleware',
]

ROOT_URLCONF = 'hospital.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [str(BASE_DIR.joinpath('Templates'))],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'hospital.wsgi.application'

# ── Database ──────────────────────────────────────────────────────────────────
# Reads DATABASE_URL env var; falls back to SQLite for local dev without Docker
_db_url = os.environ.get('DATABASE_URL')

if _db_url:
    # DATABASE_URL=postgres://user:password@db:5432/hospital
    import dj_database_url
    DATABASES = {'default': dj_database_url.parse(_db_url, conn_max_age=600)}
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }

# ── Password validation ───────────────────────────────────────────────────────
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# ── Internationalisation ──────────────────────────────────────────────────────
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# ── Static files ──────────────────────────────────────────────────────────────
STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'   # collectstatic writes here
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

# ── Media files ───────────────────────────────────────────────────────────────
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'          # mount as a Docker volume

# ── Default PK ───────────────────────────────────────────────────────────────
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ── DRF ───────────────────────────────────────────────────────────────────────
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.TokenAuthentication',
        'rest_framework.authentication.BasicAuthentication',
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
}

EMAIL_BACKEND   = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST      = 'smtp.gmail.com'
EMAIL_PORT      = 587
EMAIL_USE_TLS   = True
EMAIL_HOST_USER     = os.environ.get('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_HOST_PASSWORD', '')
DEFAULT_FROM_EMAIL  = os.environ.get('EMAIL_HOST_USER', 'noreply@carefirst.com')

# The inbox that receives contact form messages
CONTACT_RECIPIENT_EMAIL = os.environ.get('CONTACT_RECIPIENT_EMAIL', EMAIL_HOST_USER)

# ── Security headers (enable when behind HTTPS) ───────────────────────────────
if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    SECURE_SSL_REDIRECT = False  # Render's proxy handles this
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 31536000  # 1 year
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True

SPECTACULAR_SETTINGS = {
    'TITLE': 'Hospital Management System API',
    'DESCRIPTION': 'REST API for the Flutter Mobile Client, handling RBAC, appointments, and patient records.',
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
    'ENUM_NAME_OVERRIDES': {
        'AppointmentStatusEnum': 'staff.models.Appointment.STATUS_CHOICES',
        'AlertStatusEnum': 'staff.models.EmergencyAlert.ALERT_TYPES',
    },
}

SIMPLE_JWT = {
    # Extends the access token life from 5 minutes to 1 full day
    "ACCESS_TOKEN_LIFETIME": timedelta(days=1),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS": False,
    "BLACKLIST_AFTER_ROTATION": True,
    "AUTH_HEADER_TYPES": ("Bearer",),
}

CORS_ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]