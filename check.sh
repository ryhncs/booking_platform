#!/bin/sh
# Run the same checks as CI inside Docker. Usage: ./check.sh [pytest args]
set -e
cd "$(dirname "$0")"
docker compose run --rm --build web sh -c '
  ruff check . &&
  ruff format --check . &&
  python manage.py makemigrations --check --dry-run &&
  python manage.py spectacular --validate --fail-on-warn --file /dev/null &&
  pytest --cov=apps -q '"$*"'
'
