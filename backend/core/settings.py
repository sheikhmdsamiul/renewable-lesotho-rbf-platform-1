from pathlib import Path
from datetime import timedelta
import environ
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(
    DJANGO_DEBUG=(bool, True),
)
env_file = BASE_DIR / '.env'
if env_file.exists():
    environ.Env.read_env(env_file)

DEBUG = env.bool('DJANGO_DEBUG')
SECRET_KEY = env('SECRET_KEY', default='dev-secret-key')
ALLOWED_HOSTS = env.list('ALLOWED_HOSTS', default=['localhost', '127.0.0.1'])
API_REQUIRE_AUTH = env.bool('API_REQUIRE_AUTH', default=False)
FRONTEND_BASE_URL = env('FRONTEND_BASE_URL', default='http://localhost:5173')

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # 3rd party
    'rest_framework',
    'drf_spectacular',
    'django_filters',
    'corsheaders',

    # local apps
    'rbf.users',
    'rbf.tenders',
    'rbf.projects',
    'rbf.notifications',
]

AUTH_USER_MODEL = 'users.User'

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'rbf.projects.middleware.RequestContextMiddleware',
    'rbf.users.middleware.EmailConfigMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'core.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
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

WSGI_APPLICATION = 'core.wsgi.application'

DATABASES = {
    'default': env.db(default=f"postgresql://rbf_user:rbf_pass@localhost:5432/rbf"),
}
DATABASES['default']['CONN_MAX_AGE'] = env.int('DB_CONN_MAX_AGE', default=60)

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Africa/Maseru'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'
if DEBUG:
    STATICFILES_STORAGE = 'django.contrib.staticfiles.storage.StaticFilesStorage'
else:
    STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

REST_FRAMEWORK = {
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
    'DEFAULT_FILTER_BACKENDS': ['django_filters.rest_framework.DjangoFilterBackend'],
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.SessionAuthentication',
        'rest_framework.authentication.BasicAuthentication',
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': env.int('API_PAGE_SIZE', default=50),
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': env('API_THROTTLE_ANON', default='120/hour'),
        'user': env('API_THROTTLE_USER', default='600/hour'),
    },
}
if DEBUG:
    # Keep local QA/demo flows stable during repeated manual testing.
    REST_FRAMEWORK['DEFAULT_THROTTLE_CLASSES'] = []
    REST_FRAMEWORK['DEFAULT_THROTTLE_RATES'] = {}

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=env.int('JWT_ACCESS_MINUTES', default=30)),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=env.int('JWT_REFRESH_DAYS', default=7)),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': False,
}

SPECTACULAR_SETTINGS = {
    'TITLE': 'Lesotho RBF API',
    'DESCRIPTION': 'API for RBF platform',
    'VERSION': '1.0.0',
}

CORS_ALLOW_ALL_ORIGINS = env.bool('CORS_ALLOW_ALL_ORIGINS', default=DEBUG)
if not CORS_ALLOW_ALL_ORIGINS:
    CORS_ALLOWED_ORIGINS = env.list('CORS_ALLOWED_ORIGINS', default=[])

CSRF_TRUSTED_ORIGINS = env.list('CSRF_TRUSTED_ORIGINS', default=[])

# Frontend URL for email notifications and deep links. Leave blank to derive from request origin.
FRONTEND_URL = env('FRONTEND_URL', default='')
PBA_RENDER_SCRIPT = env('PBA_RENDER_SCRIPT', default=str(BASE_DIR / 'scripts' / 'render_pdf.mjs'))
PBA_CHROME_PATH = env('PBA_CHROME_PATH', default='')

if DEBUG:
    SECURE_SSL_REDIRECT = False
    SESSION_COOKIE_SECURE = False
    CSRF_COOKIE_SECURE = False
else:
    if SECRET_KEY == 'dev-secret-key' or len(SECRET_KEY) < 32:
        raise ImproperlyConfigured('SECRET_KEY must be set to a strong value (32+ chars) in production')

    SECURE_SSL_REDIRECT = env.bool('SECURE_SSL_REDIRECT', default=True)
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = env.int('SECURE_HSTS_SECONDS', default=31536000)
    SECURE_HSTS_INCLUDE_SUBDOMAINS = env.bool('SECURE_HSTS_INCLUDE_SUBDOMAINS', default=True)
    SECURE_HSTS_PRELOAD = env.bool('SECURE_HSTS_PRELOAD', default=True)
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = 'DENY'
    SECURE_REFERRER_POLICY = 'same-origin'
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

LOG_LEVEL = env('LOG_LEVEL', default='INFO')
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'standard': {
            'format': '%(asctime)s %(levelname)s %(name)s %(message)s',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'standard',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': LOG_LEVEL,
    },
}

# Cache (OTP & other short-lived state)
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.redis.RedisCache',
        'LOCATION': env('REDIS_URL', default='redis://localhost:6379/0'),
    }
}

# Email / OTP
EMAIL_BACKEND = env('EMAIL_BACKEND', default='django.core.mail.backends.smtp.EmailBackend')
EMAIL_HOST = env('EMAIL_HOST', default='smtp.gmail.com')
EMAIL_PORT = env.int('EMAIL_PORT', default=587)
EMAIL_USE_TLS = env.bool('EMAIL_USE_TLS', default=True)
EMAIL_HOST_USER = env('EMAIL_HOST_USER', default='')
EMAIL_HOST_PASSWORD = env('EMAIL_HOST_PASSWORD', default='')
DEFAULT_FROM_EMAIL = env('DEFAULT_FROM_EMAIL', default=EMAIL_HOST_USER or 'no-reply@rbf.local')
OTP_LENGTH = env.int('OTP_LENGTH', default=6)
OTP_EXPIRY_SECONDS = env.int('OTP_EXPIRY_SECONDS', default=600)

# Celery
CELERY_BROKER_URL = env('REDIS_URL', default='redis://localhost:6379/0')
CELERY_RESULT_BACKEND = env('REDIS_URL', default='redis://localhost:6379/0')
CELERY_TASK_ALWAYS_EAGER = env.bool('CELERY_TASK_ALWAYS_EAGER', default=False)

# Email dispatch: when enabled, notification emails are delivered via the
# Celery worker (requires a running worker + broker). Off by default so the
# existing single-container deployment keeps sending synchronously.
EMAIL_ASYNC = env.bool('EMAIL_ASYNC', default=False)

# Prospect integration
PROSPECT_BASE_URL = env('PROSPECT_BASE_URL', default='')
PROSPECT_API_SECRET = env('PROSPECT_API_SECRET', default='')
PROSPECT_WRITE_TOKEN = env('PROSPECT_WRITE_TOKEN', default='')
PROSPECT_READ_TOKEN = env('PROSPECT_READ_TOKEN', default=PROSPECT_API_SECRET)
PROSPECT_TOKEN_IN_AGENTS = env('PROSPECT_TOKEN_IN_AGENTS', default='')
PROSPECT_TOKEN_IN_TARGETS = env('PROSPECT_TOKEN_IN_TARGETS', default='')
PROSPECT_TOKEN_IN_CUSTOMERS = env('PROSPECT_TOKEN_IN_CUSTOMERS', default='')
PROSPECT_TOKEN_IN_INSTALLATIONS = env('PROSPECT_TOKEN_IN_INSTALLATIONS', default='')
PROSPECT_TOKEN_IN_INSTALLATIONS_TS = env('PROSPECT_TOKEN_IN_INSTALLATIONS_TS', default='')
PROSPECT_TOKEN_IN_REPORTS = env('PROSPECT_TOKEN_IN_REPORTS', default='')
PROSPECT_TOKEN_OUT_INSTALLATIONS = env('PROSPECT_TOKEN_OUT_INSTALLATIONS', default=PROSPECT_READ_TOKEN or PROSPECT_API_SECRET)
PROSPECT_TOKEN_OUT_TARGETS = env('PROSPECT_TOKEN_OUT_TARGETS', default=PROSPECT_READ_TOKEN or PROSPECT_API_SECRET)
PROSPECT_TIMEOUT_SECONDS = env.int('PROSPECT_TIMEOUT_SECONDS', default=30)
PROSPECT_BATCH_SIZE = env.int('PROSPECT_BATCH_SIZE', default=10000)

# GIS and project thresholds
LESOTHO_BOUNDARY_PATH = env('LESOTHO_BOUNDARY_PATH', default='/public/geojson/lesotho.geojson')
GPS_DUPLICATE_RADIUS_METERS = env.int('GPS_DUPLICATE_RADIUS_METERS', default=10)
GPS_VERIFICATION_MAX_DISTANCE_METERS = env.int('GPS_VERIFICATION_MAX_DISTANCE_METERS', default=50)
KPI_CACHE_MINUTES = env.int('KPI_CACHE_MINUTES', default=15)
MILESTONE2_VERIFICATION_THRESHOLD = env.float('MILESTONE2_VERIFICATION_THRESHOLD', default=0.80)
ANOMALY_DEVIATION_THRESHOLD = env.float('ANOMALY_DEVIATION_THRESHOLD', default=0.05)
MAX_MAP_RECORDS = env.int('MAX_MAP_RECORDS', default=1000)
MAX_FILE_SIZE_MB = env.int('MAX_FILE_SIZE_MB', default=10)
