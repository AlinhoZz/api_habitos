set -e

python - <<'PY'
import os
import time

import psycopg

host = os.environ.get("POSTGRES_HOST", "db")
port = int(os.environ.get("POSTGRES_PORT", "5432"))
user = os.environ.get("POSTGRES_USER", "fitness")
password = os.environ.get("POSTGRES_PASSWORD", "fitness")
dbname = os.environ.get("POSTGRES_DB", "fitness")

for i in range(60):
    try:
        with psycopg.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            dbname=dbname,
        ) as conn:
            conn.execute("SELECT 1")
            break
    except Exception:
        time.sleep(1)
else:
    raise SystemExit("Postgres não respondeu a tempo.")
PY

python manage.py migrate --noinput

exec "$@"
