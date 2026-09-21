#!/bin/sh
set -eu

read_secret() {
  file="$1"
  [ -f "$file" ] || { echo "missing secret file: $file" >&2; exit 1; }
  tr -d '\r\n' < "$file"
}

APP_PASSWORD="$(read_secret /run/secrets/postgres_app_password)"
AUDIT_PASSWORD="$(read_secret /run/secrets/postgres_audit_password)"

psql -v ON_ERROR_STOP=1 \
  --username "$POSTGRES_USER" \
  --dbname "$POSTGRES_DB" \
  --set=app_password="$APP_PASSWORD" \
  --set=audit_password="$AUDIT_PASSWORD" <<'EOSQL'
DO $do$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'aurelian_app') THEN
    CREATE ROLE aurelian_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'aurelian_audit_writer') THEN
    CREATE ROLE aurelian_audit_writer LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;
  END IF;
END
$do$;
ALTER ROLE aurelian_app PASSWORD :'app_password';
ALTER ROLE aurelian_audit_writer PASSWORD :'audit_password';
GRANT CONNECT ON DATABASE aurelian TO aurelian_app, aurelian_audit_writer;
ALTER ROLE aurelian_app SET search_path = public;
ALTER ROLE aurelian_audit_writer SET search_path = public;
EOSQL
