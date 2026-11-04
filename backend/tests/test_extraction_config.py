"""Connection setting resolution does not contact a database."""
import pytest
from psycopg.conninfo import conninfo_to_dict

from msds.preprocess.job_config import jobs_database_url


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for key in (
        "MSDS_JOBS_DATABASE_URL", "MSDS_JOBS_PG_DATABASE", "MSDS_JOBS_PG_USER",
        "MSDS_JOBS_PG_PASSWORD", "MSDS_JOBS_PG_HOST", "MSDS_JOBS_PG_PORT",
        "HTODB_PG_HOST", "HTODB_PG_PORT", "HTODB_PG_PASSWORD", "HTODB_READER_PASSWORD",
    ):
        monkeypatch.delenv(key, raising=False)


def test_explicit_url_takes_precedence(monkeypatch):
    monkeypatch.setenv("MSDS_JOBS_DATABASE_URL", "dbname=other")
    assert jobs_database_url("dbname=chosen") == "dbname=chosen"
    assert jobs_database_url() == "dbname=other"


def test_explicit_credentials_escape_password_and_use_service_address(monkeypatch):
    monkeypatch.setenv("MSDS_JOBS_PG_DATABASE", "my db")
    monkeypatch.setenv("MSDS_JOBS_PG_USER", "worker")
    monkeypatch.setenv("MSDS_JOBS_PG_PASSWORD", "secret with spaces'\\")
    monkeypatch.setenv("MSDS_JOBS_PG_HOST", "db.internal")
    monkeypatch.setenv("MSDS_JOBS_PG_PORT", "5434")
    actual = conninfo_to_dict(jobs_database_url())
    assert actual == {"host": "db.internal", "port": "5434", "dbname": "my db",
                      "user": "worker", "password": "secret with spaces'\\"}


def test_service_address_and_defaults_ignore_htodb(monkeypatch):
    for key, value in (("MSDS_JOBS_PG_DATABASE", "jobs"), ("MSDS_JOBS_PG_USER", "worker"),
                       ("MSDS_JOBS_PG_PASSWORD", "password")):
        monkeypatch.setenv(key, value)
    dsn = conninfo_to_dict(jobs_database_url())
    monkeypatch.setenv("HTODB_PG_HOST", "older")
    monkeypatch.setenv("HTODB_PG_PORT", "5555")
    dsn = conninfo_to_dict(jobs_database_url())
    assert (dsn["host"], dsn["port"]) == ("127.0.0.1", "5432")
    monkeypatch.setenv("MSDS_JOBS_PG_HOST", "newer")
    monkeypatch.setenv("MSDS_JOBS_PG_PORT", "5440")
    dsn = conninfo_to_dict(jobs_database_url())
    assert (dsn["host"], dsn["port"]) == ("newer", "5440")


def test_missing_credentials_never_uses_htodb_passwords(monkeypatch):
    monkeypatch.setenv("HTODB_PG_PASSWORD", "sensitive")
    monkeypatch.setenv("HTODB_READER_PASSWORD", "sensitive")
    with pytest.raises(ValueError, match="MSDS_JOBS_PG_DATABASE") as err:
        jobs_database_url()
    assert "sensitive" not in str(err.value)


@pytest.mark.parametrize("port", ["0", "65536", "abc", " "])
def test_invalid_port(monkeypatch, port):
    for key, value in (("MSDS_JOBS_PG_DATABASE", "jobs"), ("MSDS_JOBS_PG_USER", "worker"),
                       ("MSDS_JOBS_PG_PASSWORD", "password"), ("MSDS_JOBS_PG_PORT", port)):
        monkeypatch.setenv(key, value)
    with pytest.raises(ValueError, match="port"):
        jobs_database_url()


def test_whitespace_credentials_rejected(monkeypatch):
    monkeypatch.setenv("MSDS_JOBS_PG_DATABASE", "jobs")
    monkeypatch.setenv("MSDS_JOBS_PG_USER", "worker")
    monkeypatch.setenv("MSDS_JOBS_PG_PASSWORD", "   ")
    with pytest.raises(ValueError, match="MSDS_JOBS_PG_PASSWORD"):
        jobs_database_url()
