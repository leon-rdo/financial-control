# financial-control
 Sistema de Gestão de Despesas e Entradas Financeiras Pessoais

## Assistente no Telegram

Envie ao bot comprovantes (foto), faturas de cartão e extratos (PDF, CSV, OFX) ou texto livre. O assistente monta um **lote** com os lançamentos, marca o que já está registrado e mostra um resumo com o botão **Confirmar**. Nada é gravado sem essa confirmação. Ele também responde perguntas ("quanto vou pagar de fatura em dezembro?", "qual meu saldo previsto em janeiro?") e manda avisos automáticos (fatura vencendo, saldo projetado negativo, resumo mensal).

Como os dados ficam organizados:

- **Fatura com vários cartões** (titular, adicional, virtual): cada compra fica no cartão que a fez; os cartões adicionais são ligados ao principal ("Cobrado na fatura de"), então a fatura, o vencimento e o pagamento continuam únicos.
- **Caixinhas / cofrinhos**: são subcontas ("Caixinha / cofrinho da conta"). Guardar e retirar dinheiro vira transferência, não gasto. O saldo disponível mostra só as contas; o guardado aparece à parte. Como o extrato da conta não traz o saldo da caixinha, informe-o ao bot ("tenho 8.000 na caixinha Emergências").

Comandos no chat: `/novo` (nova conversa), `/desfazer` (desfaz o último lote confirmado), `/cancelar`, `/ajuda`.

### Configuração (`.env`)

```
TELEGRAM_BOT_TOKEN=...
TELEGRAM_WEBHOOK_SECRET=...          # letras, números, _ e -
TELEGRAM_ALLOWED_CHAT_IDS=123456789  # obrigatório: vazio = ninguém é atendido
AI_PROVIDER=anthropic                # ou openai
ANTHROPIC_API_KEY=...
ANTHROPIC_MODEL=claude-opus-5-5      # opcional
ANTHROPIC_EFFORT=medium              # opcional: low | medium | high
OPENAI_API_KEY=...                   # só com AI_PROVIDER=openai
PDF_PASSWORDS=12345                  # opcional: senhas tentadas em PDFs protegidos
```

### Desenvolvimento local

```bash
uv sync --no-install-project        # cria .venv a partir do uv.lock
python manage.py migrate
python manage.py runserver
python manage.py test financial assistant telegram_bot
```

O site exige login (`/entrar/`); crie um usuário com `python manage.py createsuperuser`.

Para testar o bot sem URL pública (atenção: o webhook de produção precisa ser reconfigurado depois):

```bash
python manage.py setup_telegram_webhook --delete
python manage.py run_telegram_worker --poll
```

## Produção (confin.site)

Servidor `leonardo_contabo` (alias em `~/.ssh/config`), app em `/var/www/confin`:

| Peça | O que é |
|---|---|
| `confin.service` | site + webhook (gunicorn em 127.0.0.1:8030, atrás do nginx) |
| `confin-worker.service` | worker do bot (chama a IA) |
| `confin-digests.timer` | avisos automáticos, todo dia às 8h de Brasília |
| PostgreSQL | banco `confin`, usuário `confin` |
| `/var/www/confin/.env` | segredos de produção (só no servidor) |
| `/var/www/confin/data/` | arquivos recebidos pelo bot e cache |

Publicar uma nova versão:

```bash
deploy/deploy.sh
```

O script copia o código (rsync), instala dependências, roda as migrações, coleta estáticos e reinicia os serviços. Não mexe no `.env`, em `data/` nem na configuração do nginx.

Úteis no servidor:

```bash
journalctl -u confin -u confin-worker -f                 # logs
systemctl status confin confin-worker confin-digests.timer
cd /var/www/confin && set -a && . ./.env && set +a && .venv/bin/python manage.py send_digests --dry-run
```

A primeira instalação criou: usuário de sistema `confin`, banco e usuário no PostgreSQL, `/etc/nginx/sites-available/confin` (a partir de `deploy/nginx-confin.conf`, depois ajustado pelo certbot), `/etc/nginx/conf.d/confin-ratelimit.conf` e os units de `deploy/`.
