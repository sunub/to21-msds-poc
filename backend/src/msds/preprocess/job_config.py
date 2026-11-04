"""Connection settings for the separate writable extraction jobs database."""
from __future__ import annotations

import os

from psycopg.conninfo import make_conninfo


def jobs_database_url(explicit_url: str | None = None) -> str:
    """Resolve a job DB DSN or build one from explicitly supplied credentials.

    Database, user and password must always be supplied for jobs. The default
    service address is 127.0.0.1:5432. No connection is made by this function.
    """
    if explicit_url is not None:
        if not explicit_url.strip():
            raise ValueError("The explicit jobs database URL is empty")
        return explicit_url.strip()

    url = os.environ.get("MSDS_JOBS_DATABASE_URL")
    if url is not None:
        if not url.strip():
            raise ValueError("MSDS_JOBS_DATABASE_URL is empty")
        return url.strip()

    fields = {
        "MSDS_JOBS_PG_DATABASE": os.environ.get("MSDS_JOBS_PG_DATABASE"),
        "MSDS_JOBS_PG_USER": os.environ.get("MSDS_JOBS_PG_USER"),
        "MSDS_JOBS_PG_PASSWORD": os.environ.get("MSDS_JOBS_PG_PASSWORD"),
    }
    missing = [key for key, value in fields.items() if value is None or not value.strip()]
    if missing:
        raise ValueError("Configure MSDS_JOBS_DATABASE_URL or set " + ", ".join(missing))
    host = (os.environ.get("MSDS_JOBS_PG_HOST") or "127.0.0.1").strip()
    port = (os.environ.get("MSDS_JOBS_PG_PORT") or "5432").strip()
    if not host:
        raise ValueError("PostgreSQL jobs host is empty")
    if not port.isascii() or not port.isdecimal() or not 1 <= int(port) <= 65535:
        raise ValueError("PostgreSQL jobs port must be between 1 and 65535")
    return make_conninfo(
        host=host,
        port=port,
        dbname=fields["MSDS_JOBS_PG_DATABASE"].strip(),
        user=fields["MSDS_JOBS_PG_USER"].strip(),
        password=fields["MSDS_JOBS_PG_PASSWORD"],
    )
