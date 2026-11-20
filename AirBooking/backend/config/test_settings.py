"""Use file-backed SQLite for realistic concurrent-transaction tests.

SQLite shared in-memory test databases raise SQLITE_LOCKED immediately instead
of honoring busy_timeout; a temporary file exercises the production lock mode.
PostgreSQL keeps Django's standard test database behavior.
"""
import atexit
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory

from .settings import *  # noqa: F403

DATABASES = deepcopy(DATABASES)
if DATABASES["default"]["ENGINE"] == "django.db.backends.sqlite3":
    _test_directory = TemporaryDirectory(prefix="airbooking-tests-")
    atexit.register(_test_directory.cleanup)
    DATABASES["default"]["TEST"] = {"NAME": str(Path(_test_directory.name) / "tests.sqlite3")}
