# financial-control
 Sistema de Gestão de Despesas e Entradas Financeiras Pessoais

Como usar no dia a dia (primeiro uso, o que mandar ao bot, cartão emprestado, dicas): [docs/GUIA.md](docs/GUIA.md).

## Assistente no Telegram

Envie ao bot comprovantes (foto), faturas de cartão e extratos (PDF, CSV, OFX) ou texto livre. O assistente monta um **lote** com os lançamentos, marca o que já está registrado e mostra um resumo com o botão **Confirmar**. Nada é gravado sem essa confirmação. Ele também responde perguntas ("quanto vou pagar de fatura em dezembro?", "qual meu saldo previsto em janeiro?") e manda avisos automáticos (fatura vencendo, saldo projetado negativo, resumo mensal).

Como os documentos são lidos:

- PDF, CSV e OFX são lidos por um modelo mais barato, numa chamada só. O servidor confere o resultado (soma da fatura, saldo do extrato e cada item contra a linha original) antes de mostrar o lote. Se algo não fechar, ele tenta de novo, depois usa um modelo mais forte e, por último, o assistente completo.
- `ASSISTANT_DOCUMENT_MODE=batch` (padrão): a leitura vai para a fila de batches da Anthropic, pela metade do preço, e o bot avisa quando o lote fica pronto (em geral alguns minutos). Para ler na hora, envie o arquivo com a legenda `agora`, ou use `direct` no `.env`. `agent` volta ao fluxo antigo, em que o assistente completo lê o documento.
- Fotos de comprovante, texto e perguntas continuam sendo respondidos na hora pelo assistente.
- Custo medido numa fatura real de 199 linhas, em batch: Sonnet 5.5 (padrão) cerca de US$ 0,17, idêntica ao PDF em todas as leituras; Haiku 5.5 cerca de US$ 0,01, com os totais sempre certos mas pequenos desvios em parte das leituras (`ANTHROPIC_EXTRACTION_MODEL=claude-haiku-5-5` para priorizar custo). O fluxo antigo, com o assistente completo, custava US$ 0,81.

Como os dados ficam organizados:

- **Fatura com vários cartões** (titular, adicional, virtual): cada compra fica no cartão que a fez; os cartões adicionais são ligados ao principal ("Cobrado na fatura de"), então a fatura, o vencimento e o pagamento continuam únicos.
- **Caixinhas / cofrinhos**: são subcontas ("Caixinha / cofrinho da conta"). Guardar e retirar dinheiro vira transferência, não gasto. O saldo disponível mostra só as contas; o guardado aparece à parte. Como o extrato da conta não traz o saldo da caixinha, informe-o ao bot ("tenho 8.000 na caixinha Emergências").

- **Casal / família**: as finanças são conjuntas e todos veem tudo. Cadastre as pessoas dizendo ao bot ("sou o João, nos documentos apareço como JOAO DA SILVA; cadastre minha esposa Maria") e de quem é cada conta ("o Inter é da Maria"), ou pelo admin e pelos formulários de conta e de método de pagamento. Com isso o bot sabe quem está falando, trata Pix entre vocês como transferência (não como gasto de um e receita do outro) e mostra gastos e saldos por pessoa.

- **Cartão emprestado**: compras de pessoas de fora da família no cartão de vocês são marcadas com a pessoa ("os itens 12 e 40 são do João"). Continuam na fatura e na previsão, mas saem dos gastos da família; a devolução não conta como receita, e o sistema mostra quanto cada pessoa deve (`/terceiros`). Um cartão que fica com outra pessoa pode ser marcado como emprestado, e tudo nele passa a ser dela por padrão.
- **Regras permanentes**: o que você responde uma vez ("Pix para a minha empresa é gasto") fica guardado e vale para os próximos documentos.

Comandos no chat: `/novo` (nova conversa), `/desfazer` (desfaz o último lote confirmado), `/terceiros` (quem deve quanto), `/custo` (gasto com IA no mês), `/cancelar`, `/ajuda`.

Gasto com IA: cada chamada grava o uso de tokens, e `assistant/costs.py` converte em dólares pela tabela de preços. `AI_MONTHLY_BUDGET_USD` é o orçamento do mês (e-mail aos 80% e aos 100%) e `AI_MONTHLY_LIMIT_USD` é o teto: ao chegar nele o bot para de chamar a IA até o mês virar (comandos, botões e avisos continuam).

### Configuração (`.env`)

```
TELEGRAM_BOT_TOKEN=...
TELEGRAM_WEBHOOK_SECRET=...          # letras, números, _ e -
TELEGRAM_ALLOWED_CHAT_IDS=123456789  # obrigatório: vazio = ninguém é atendido
AI_PROVIDER=anthropic                # ou openai
ANTHROPIC_API_KEY=...
ANTHROPIC_MODEL=claude-opus-5-5      # opcional
ANTHROPIC_EFFORT=medium              # opcional: low | medium | high
ASSISTANT_DOCUMENT_MODE=batch        # opcional: batch | direct | agent (ver abaixo)
ANTHROPIC_EXTRACTION_MODEL=claude-sonnet-5-5         # opcional: modelo que lê os documentos
ANTHROPIC_EXTRACTION_FALLBACK_MODEL=claude-opus-5-5  # opcional: usado se as conferências falharem
OPENAI_API_KEY=...                   # só com AI_PROVIDER=openai
PDF_PASSWORDS=12345                  # opcional: senhas tentadas em PDFs protegidos
AI_MONTHLY_BUDGET_USD=20             # opcional: orçamento mensal de IA em dólares (0 desliga os avisos)
AI_MONTHLY_LIMIT_USD=40              # opcional: teto mensal; ao atingir, o bot para de usar IA (0 = sem teto)
ALERT_EMAIL=voce@exemplo.com         # quem recebe os avisos (gasto com IA, falha de backup)
EMAIL_HOST=smtp.exemplo.com          # sem EMAIL_HOST os avisos saem só no log
EMAIL_HOST_USER=...
EMAIL_HOST_PASSWORD=...
DEFAULT_FROM_EMAIL=no-reply@exemplo.com
```

### Desenvolvimento local

```bash
uv sync --no-install-project        # cria .venv a partir do uv.lock
python manage.py migrate
python manage.py runserver
python manage.py test core financial assistant telegram_bot
```

O site exige login (`/entrar/`); crie um usuário com `python manage.py createsuperuser`.

Para testar o bot sem URL pública, use um **bot separado para desenvolvimento** (assim o de produção não é afetado):

1. No Telegram, fale com `@BotFather`: `/newbot`, escolha um nome (ex.: "Confin Dev") e um usuário terminado em `bot`. Ele devolve o token.
2. No `.env` local: `TELEGRAM_BOT_TOKEN=<token do bot de dev>`, `TELEGRAM_ALLOWED_CHAT_IDS=<seu chat>` e `ASSISTANT_DOCUMENT_MODE=direct` (resposta na hora). `TELEGRAM_WEBHOOK_SECRET` não é usado no modo polling.
3. Rode o worker em modo polling e converse com o bot de dev:

```bash
python manage.py run_telegram_worker --poll
```

Um bot novo não tem webhook, então nada precisa ser removido. Nunca use `setup_telegram_webhook --delete` com o token de produção: o bot de produção para de receber mensagens até o webhook ser configurado de novo.

## Produção (confin.site)

Servidor `leonardo_contabo` (alias em `~/.ssh/config`), app em `/var/www/confin`:

| Peça | O que é |
|---|---|
| `confin.service` | site + webhook (gunicorn em 127.0.0.1:8030, atrás do nginx) |
| `confin-worker.service` | worker do bot (chama a IA) |
| `confin-digests.timer` | avisos automáticos, todo dia às 8h de Brasília |
| `confin-backup.timer` | backup do banco e dos arquivos, todo dia às 3h30, em `/var/backups/confin` |
| PostgreSQL | banco `confin`, usuário `confin` |
| `/var/www/confin/.env` | segredos de produção (só no servidor) |
| `/var/www/confin/data/` | arquivos recebidos pelo bot e cache |

Publicar uma nova versão:

```bash
deploy/deploy.sh
```

O script copia o código (rsync), instala dependências, roda os testes no servidor (contra o PostgreSQL, no banco `test_confin`), aplica as migrações, coleta estáticos e reinicia os serviços. Se um teste falhar, ele para antes de migrar e de reiniciar. Não mexe no `.env`, em `data/` nem na configuração do nginx.

Backup: `python manage.py backup_data` gera `db-<data>.dump` (formato do `pg_restore`) e `files-<data>.tar.gz` (arquivos recebidos pelo bot), confere o dump, mantém os últimos 14 dias e o do dia 1 de cada mês por 12 meses, e manda e-mail se falhar. Os backups ficam no mesmo servidor; copie `/var/backups/confin` para outro lugar para ter proteção contra a perda da máquina. Restaurar:

```bash
pg_restore --clean --if-exists --no-owner -d confin /var/backups/confin/db-<data>.dump
tar -xzf /var/backups/confin/files-<data>.tar.gz -C /var/www/confin/data
```

Úteis no servidor:

```bash
journalctl -u confin -u confin-worker -f                 # logs
systemctl status confin confin-worker confin-digests.timer confin-backup.timer
systemctl start confin-backup && ls -la /var/backups/confin   # backup agora
cd /var/www/confin && set -a && . ./.env && set +a && .venv/bin/python manage.py send_alert "teste"   # testa o e-mail
cd /var/www/confin && set -a && . ./.env && set +a && .venv/bin/python manage.py send_digests --dry-run
```

A primeira instalação criou: usuário de sistema `confin`, banco e usuário no PostgreSQL, `/etc/nginx/sites-available/confin` (a partir de `deploy/nginx-confin.conf`, depois ajustado pelo certbot), `/etc/nginx/conf.d/confin-ratelimit.conf` e os units de `deploy/`.
