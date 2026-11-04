#!/bin/bash
# Pod 안: 앱 가상환경(볼륨), PostgreSQL 16(컨테이너 디스크), 지식DB 복원, 서비스 DB, Apache(8080, Basic 인증).
# 처음과 Pod를 다시 켤 때마다 실행한다(컨테이너 디스크의 PostgreSQL·Apache·DB가 지워지므로).
# 네트워크 볼륨(/workspace)은 소유자 변경이 안 돼 PostgreSQL 데이터를 둘 수 없다. 그래서 Pod를 켤 때마다 덤프에서 복원한다.
# 다시 실행해도 된다. 비밀번호는 deploy/htodb/.env 와 /workspace/web_password 에서만 읽고 출력하지 않는다.
set -euo pipefail
W=/workspace; APP=$W/to21; PGBIN=/usr/lib/postgresql/16/bin; PGDATA=/var/lib/postgresql/to21
set -a; . $APP/deploy/htodb/.env; set +a
PORT=${HTODB_PG_PORT:-5433}
export DEBIAN_FRONTEND=noninteractive

echo "[0] 앱 가상환경 (볼륨에 있으면 건너뜀)"
if [ ! -x $APP/backend/.venv/bin/python ]; then
  command -v uv >/dev/null || { curl -LsSf https://astral.sh/uv/install.sh | sh >/dev/null 2>&1; }
  export PATH=$HOME/.local/bin:$PATH
  ( cd $APP/backend && UV_LINK_MODE=copy uv sync --frozen --no-dev --python 3.11 > $W/venv_app.log 2>&1 )
fi

echo "[1] 패키지"
if [ ! -x $PGBIN/postgres ] || ! command -v apache2 >/dev/null; then
  apt-get update -qq && apt-get install -y -qq postgresql-16 apache2 apache2-utils >/dev/null
fi
service postgresql stop >/dev/null 2>&1 || true

echo "[2] PostgreSQL ($PGDATA, 포트 $PORT)"
if [ ! -s $PGDATA/PG_VERSION ]; then
  mkdir -p $PGDATA && chown postgres:postgres $PGDATA && chmod 700 $PGDATA
  printf '%s' "$HTODB_PG_PASSWORD" > /tmp/pgpw && chown postgres /tmp/pgpw
  su postgres -c "$PGBIN/initdb -D $PGDATA -U kdb --pwfile=/tmp/pgpw -A scram-sha-256 -E UTF8 --locale=C.UTF-8" >/dev/null
  rm -f /tmp/pgpw
fi
su postgres -c "$PGBIN/pg_ctl -D $PGDATA -o '-p $PORT -c listen_addresses=127.0.0.1' -l $PGDATA/server.log status" >/dev/null 2>&1 \
  || su postgres -c "$PGBIN/pg_ctl -D $PGDATA -o '-p $PORT -c listen_addresses=127.0.0.1' -l $PGDATA/server.log -w start" >/dev/null
export PGPASSWORD="$HTODB_PG_PASSWORD" PGHOST=127.0.0.1 PGPORT=$PORT PGUSER=kdb

echo "[3] 역할과 지식DB 복원"
if ! psql -d postgres -Atc "select 1 from pg_database where datname='kdb'" | grep -q 1; then
  grep -v "^CREATE ROLE kdb;" $W/globals.sql | grep -v "^ALTER ROLE kdb " | psql -q -d postgres >/dev/null
  createdb kdb
  pg_restore -d kdb --no-owner --role=kdb $W/kdb.dump || true   # 역할 소유 경고는 무시하고 아래에서 표 수로 확인
fi
KDB_TABLES=$(psql -d kdb -Atc "select count(*) from pg_tables where schemaname in ('htodb','htodb_map')")
echo "  지식DB 표: $KDB_TABLES"
[ "$KDB_TABLES" -gt 0 ] || { echo "지식DB 복원 실패. dropdb kdb 후 다시 실행" >&2; exit 1; }

echo "[4] 서비스 DB(msds_service)"
if ! psql -d postgres -Atc "select 1 from pg_database where datname='msds_service'" | grep -q 1; then
  createdb msds_service
  ( cd $APP && TO21_ERD_DATABASE_URL="host=127.0.0.1 port=$PORT dbname=msds_service user=kdb" \
      backend/.venv/bin/python backend/scripts/apply_erd_migrations.py --extract-role to21_extract --judge-role to21_judge >/dev/null )
  ( cd $APP/backend && PYTHONPATH=src .venv/bin/python scripts/b2_migrate.py --database msds_service >/dev/null )
fi
SVC_TABLES=$(psql -d msds_service -Atc "select count(*) from pg_tables where schemaname in ('extract','judge')")
echo "  서비스 DB 표: $SVC_TABLES"
[ "$SVC_TABLES" -gt 0 ] || { echo "서비스 DB 준비 실패. dropdb msds_service 후 다시 실행" >&2; exit 1; }

echo "[5] Apache 8080 → 앱 8020 (Basic 인증)"
[ -s $W/web_password ] || { head -c 24 /dev/urandom | base64 | tr -dc A-Za-z0-9 | head -c 16 > $W/web_password; chmod 600 $W/web_password; }
htpasswd -cbB /etc/apache2/to21.htpasswd to21 "$(cat $W/web_password)" >/dev/null 2>&1
a2enmod -q proxy proxy_http headers auth_basic >/dev/null
grep -q "^Listen 8080" /etc/apache2/ports.conf || echo "Listen 8080" >> /etc/apache2/ports.conf
sed -i 's/^Listen 80$/# Listen 80/' /etc/apache2/ports.conf
cat > /etc/apache2/sites-available/to21.conf <<'CONF'
<VirtualHost *:8080>
    ProxyPreserveHost On
    ProxyTimeout 600
    LimitRequestBody 52428800
    <Location />
        AuthType Basic
        AuthName "TO21 MSDS"
        AuthUserFile /etc/apache2/to21.htpasswd
        Require valid-user
    </Location>
    # 앱(uvicorn)은 쉬는 연결을 5초 뒤 닫는다. 재사용하면 진행 조회가 가끔 502가 된다(2026-11-04 체험 서버에서 재현)
    ProxyPass / http://127.0.0.1:8020/ disablereuse=On
    ProxyPassReverse / http://127.0.0.1:8020/
</VirtualHost>
CONF
a2dissite -q 000-default >/dev/null 2>&1 || true
a2ensite -q to21 >/dev/null
service apache2 restart >/dev/null && echo "  Apache OK"
echo "끝"
