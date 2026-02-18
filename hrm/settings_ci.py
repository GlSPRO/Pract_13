from .settings import *  # noqa: F401,F403

# CI build/static check needs an explicit destination.
STATIC_ROOT = BASE_DIR / "staticfiles_ci"
