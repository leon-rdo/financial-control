#!/usr/bin/env bash
# Publica o código atual no servidor e reinicia os serviços.
#
#   deploy/deploy.sh [host-ssh]        (padrão: leonardo_contabo)
#
# Não toca em .env, data/ nem no banco (só roda as migrações pendentes).
# A primeira instalação (usuário, banco, nginx, certificado) está descrita no README.
set -euo pipefail

HOST="${1:-leonardo_contabo}"
APP=/var/www/confin
cd "$(dirname "$0")/.."

rsync -az --delete \
    --exclude '.git/' --exclude '.venv/' --exclude '.env' --exclude '.claude/' \
    --exclude 'db.sqlite3*' --exclude 'private/' --exclude 'media/' --exclude 'data/' \
    --exclude 'staticfiles/' --exclude '__pycache__/' --exclude '*.pyc' \
    ./ "$HOST:$APP/"

ssh "$HOST" bash -s <<'REMOTE'
set -euo pipefail  # pipefail: falha de teste derruba o deploy mesmo passando pelo `tail`
cd /var/www/confin
uv sync --frozen --extra prod --no-install-project --python 3.12 --quiet
set -a; . ./.env; set +a
# Testes contra o PostgreSQL do servidor, no banco fixo `test_confin` (o usuário
# do app não cria bancos). Se falharem, o deploy para aqui: nada é migrado nem reiniciado.
.venv/bin/python manage.py test financial assistant telegram_bot --keepdb --noinput 2>&1 \
    | grep -E "^(Ran |OK|FAILED|FAIL:|ERROR:)"
.venv/bin/python manage.py migrate --noinput
.venv/bin/python manage.py collectstatic --noinput --verbosity 0
chown -R root:www-data . && chmod -R g-w,o-rwx .
chown -R confin:www-data data && chown confin:www-data .env && chmod 600 .env
for unit in confin.service confin-worker.service confin-digests.service confin-digests.timer; do
    install -m 644 "deploy/$unit" "/etc/systemd/system/$unit"
done
systemctl daemon-reload
systemctl restart confin confin-worker
sleep 3
systemctl is-active confin confin-worker confin-digests.timer
REMOTE
echo "Publicado em $HOST."
