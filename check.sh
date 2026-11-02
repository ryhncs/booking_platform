#!/bin/sh
# Run the same checks as CI inside Docker. Usage: ./check.sh [pytest args]
set -e
cd "$(dirname "$0")"

echo "== backend"
docker compose run --rm --build web sh -c '
  ruff check . &&
  ruff format --check . &&
  python manage.py makemigrations --check --dry-run &&
  python manage.py spectacular --validate --fail-on-warn --file /dev/null &&
  pytest --cov=apps -q '"$*"'
'

echo "== frontend"
# npm writes node_modules/.package-lock.json on every install; if it is newer
# than package-lock.json the installed modules are current and `npm ci` is skipped.
docker compose run --rm --no-deps frontend sh -c '
  { [ node_modules/.package-lock.json -nt package-lock.json ] || npm ci --no-audit --no-fund; } &&
  npm run check
'
