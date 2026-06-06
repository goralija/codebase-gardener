from pathlib import Path

import environ


BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(
    DJANGO_DEBUG=(bool, False),
    DJANGO_ALLOWED_HOSTS=(list, ["localhost", "127.0.0.1"]),
    DJANGO_CORS_ALLOWED_ORIGINS=(
        list,
        [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:5174",
            "http://127.0.0.1:5174",
        ],
    ),
    DJANGO_CSRF_TRUSTED_ORIGINS=(
        list,
        [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:5174",
            "http://127.0.0.1:5174",
        ],
    ),
)
environ.Env.read_env(BASE_DIR.parent / ".env")

SECRET_KEY = env("DJANGO_SECRET_KEY", default="dev-insecure-change-me")
DEBUG = env("DJANGO_DEBUG")
ALLOWED_HOSTS = env("DJANGO_ALLOWED_HOSTS")
CORS_ALLOWED_ORIGINS = env("DJANGO_CORS_ALLOWED_ORIGINS")
CORS_ALLOW_CREDENTIALS = True
CORS_URLS_REGEX = r"^/api/.*$"
CSRF_TRUSTED_ORIGINS = env("DJANGO_CSRF_TRUSTED_ORIGINS")

GITHUB_APP_SLUG = env("GITHUB_APP_SLUG", default="codebase-gardener")
GITHUB_APP_ID = env("GITHUB_APP_ID", default="")
GITHUB_APP_CLIENT_ID = env("GITHUB_APP_CLIENT_ID", default="")
GITHUB_APP_CLIENT_SECRET = env("GITHUB_APP_CLIENT_SECRET", default="")
GITHUB_APP_PRIVATE_KEY = env("GITHUB_APP_PRIVATE_KEY", default="")
GITHUB_WEBHOOK_SECRET = env("GITHUB_WEBHOOK_SECRET", default="")
GITHUB_API_BASE_URL = env("GITHUB_API_BASE_URL", default="https://api.github.com")
GITHUB_WEB_BASE_URL = env("GITHUB_WEB_BASE_URL", default="https://github.com")
GITHUB_API_VERSION = env("GITHUB_API_VERSION", default="2022-11-28")
FRONTEND_REDIRECT_BASE_URL = env(
    "FRONTEND_REDIRECT_BASE_URL",
    default="http://localhost:5173",
)

# S3-compatible object storage (MinIO locally, Cloudflare R2 in production).
# Same code path; only endpoint + credentials differ between environments.
OBJECT_STORAGE_ENDPOINT_URL = env(
    "OBJECT_STORAGE_ENDPOINT_URL", default="http://localhost:19000"
)
OBJECT_STORAGE_ACCESS_KEY = env("OBJECT_STORAGE_ACCESS_KEY", default="local")
OBJECT_STORAGE_SECRET_KEY = env("OBJECT_STORAGE_SECRET_KEY", default="localpass123")
OBJECT_STORAGE_BUCKET = env("OBJECT_STORAGE_BUCKET", default="gardener-analysis")
OBJECT_STORAGE_REGION = env("OBJECT_STORAGE_REGION", default="auto")

# LLM (OpenRouter) used by the AI code-fix author.
OPENROUTER_API_KEY = env("OPENROUTER_API_KEY", default="")
OPENROUTER_BASE_URL = env("OPENROUTER_BASE_URL", default="https://openrouter.ai/api/v1")
OPENROUTER_MODEL = env("OPENROUTER_MODEL", default="deepseek/deepseek-chat")
OPENROUTER_TIMEOUT_SECONDS = env.float("OPENROUTER_TIMEOUT_SECONDS", default=120.0)

# Hosted analysis worker settings.
ANALYSIS_REPOWISE_PROJECT_DIR = env(
    "ANALYSIS_REPOWISE_PROJECT_DIR",
    default=str(BASE_DIR.parent / "RepoWise"),
)
ANALYSIS_CLONE_DEPTH = env.int("ANALYSIS_CLONE_DEPTH", default=100)
ANALYSIS_CLONE_TIMEOUT_SECONDS = env.int("ANALYSIS_CLONE_TIMEOUT_SECONDS", default=600)

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "corsheaders",
    "rest_framework",
    "apps.common.apps.CommonConfig",
    "apps.accounts.apps.AccountsConfig",
    "apps.github_app.apps.GitHubAppConfig",
    "apps.repositories.apps.RepositoriesConfig",
    "apps.constitution.apps.ConstitutionConfig",
    "apps.analysis.apps.AnalysisConfig",
    "apps.entropy.apps.EntropyConfig",
    "apps.sessions.apps.SessionsConfig",
    "apps.maintenance_prs.apps.MaintenancePRsConfig",
    "apps.profiles.apps.ProfilesConfig",
    "apps.triggers.apps.TriggersConfig",
    "apps.billing.apps.BillingConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DATABASES = {
    "default": env.db(
        "DATABASE_URL",
        default="postgres://gardener:gardener@localhost:15432/gardener",
    )
}

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
AUTH_USER_MODEL = "accounts.User"

REST_FRAMEWORK = {
    "EXCEPTION_HANDLER": "apps.common.api.api_exception_handler",
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
}

CELERY_BROKER_URL = env("REDIS_URL", default="redis://localhost:16379/0")
CELERY_RESULT_BACKEND = CELERY_BROKER_URL
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = "UTC"
CELERY_TASK_TRACK_STARTED = True
CELERY_BEAT_SCHEDULE = {
    "dispatch-scheduled-sessions": {
        "task": "apps.triggers.tasks.dispatch_scheduled_sessions",
        "schedule": env.float("SCHEDULED_SESSIONS_INTERVAL_SECONDS", default=24 * 60 * 60),
    },
}
