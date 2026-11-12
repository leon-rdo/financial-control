# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**financial-control** is a Django-based personal finance management application for tracking expenses, income, installment-based purchases, and recurrences. Built with Django 6+, HTMX for dynamic UI, a hand-written design system (`static/css/confin.css`, no Tailwind/DaisyUI), Alpine.js, and Select2 for searchable dropdowns on desktop.

## Commands

```bash
uv sync --no-install-project       # Cria/atualiza .venv (Python 3.12) a partir do uv.lock
source .venv/bin/activate

python manage.py runserver         # Dev server on :8000
python manage.py makemigrations    # After model changes
python manage.py migrate           # Apply migrations

# Telegram bot: webhook só enfileira; o worker processa (IA)
python manage.py setup_telegram_webhook --url <public_url>/telegram/webhook/<TELEGRAM_WEBHOOK_SECRET>/
python manage.py setup_telegram_webhook --delete  # Remove webhook
python manage.py run_telegram_worker              # Worker (produção, junto com o webhook)
python manage.py run_telegram_worker --poll       # Dev local sem URL pública (exige webhook removido)

python manage.py send_digests [--dry-run] [--date AAAA-MM-DD]  # Avisos automáticos (1x/dia)

python manage.py backup_data [--dir DIR]   # Backup do banco + arquivos do bot (diário em produção)
python manage.py send_alert "assunto"      # Testa o e-mail de avisos (ALERT_EMAIL)

python manage.py test core financial assistant telegram_bot  # Testes (Django TestCase)

deploy/deploy.sh                   # Publica em produção (confin.site, host ssh leonardo_contabo)
```

No linter is configured. O extra `prod` (gunicorn + psycopg) é instalado pelo `deploy/deploy.sh`, que também roda os testes no servidor antes de publicar.

## Production

`https://confin.site` em `/var/www/confin` (host ssh `leonardo_contabo`): nginx → gunicorn `confin.service` (127.0.0.1:8030), `confin-worker.service` (bot), `confin-digests.timer` (8h de Brasília), `confin-backup.timer` (3h30, `/var/backups/confin`), PostgreSQL local (`DB_USED=postgres`). Segredos só no `.env` do servidor. Arquivos em `deploy/`; `deploy/deploy.sh` faz rsync + `uv sync` + `migrate` + `collectstatic` + restart. Logs: `journalctl -u confin -u confin-worker -f`.

## Architecture

### Django Project: `financial_control/`

Settings in `financial_control/settings.py`. Database defaults to SQLite; set `DB_USED=mysql` or `DB_USED=postgres` (production) to switch. Root URL conf mounts apps at `/` (core, accounts, financial) and `/telegram/` (telegram_bot).

### Apps

- **`core/`** — Reference data: `Category` (INCOME/EXPENSE/BOTH), `Tag`, `Entity` (SUPPLIER/EMPLOYER/CLIENT/PERSON/OTHER; PERSON = pessoa de fora da família, usada no cartão emprestado). Has CNPJ lookup API (`fetch_cnpj_data`). Contains `HTMXMiddleware` (`core/middleware.py`) that sets `request.htmx` boolean from `HX-Request` header.

- **`accounts/`** — `BankAccount`, `PaymentMethod` (PIX/DEBIT/CREDIT/CASH/TRANSFER/BOLETO). Credit cards have `closing_day`, `due_day`, `credit_limit`. Has bank lookup API (`fetch_banks` via BrasilAPI).
  - Caixinhas/cofrinhos: `BankAccount.parent` (dinheiro guardado dentro de outra conta; `is_reserve`, fora do saldo disponível). Reservar/retirar é `financial.Transfer` entre a conta e a caixinha, nunca despesa.
  - Fatura conjunta: `PaymentMethod.billing_card` liga cartão adicional/virtual ao cartão principal. Cada compra fica no cartão que a fez; fechamento, vencimento, previsão e pagamento são do principal (`invoice_card`, `forecast.card_family_ids`).
  - `BalanceSnapshot` = saldo conhecido de uma conta/caixinha numa data.
  - Família (finanças conjuntas): `core.FamilyMember` (nome, nomes como aparecem em documentos, chat do Telegram). `BankAccount.holder` e `PaymentMethod.holder` dizem de quem é cada conta/cartão (`effective_holder`: caixinha herda da conta; método herda da conta ou do cartão principal). Não há permissão por pessoa: todos veem tudo; o titular serve para relatórios por pessoa (`spending_summary(group_by="holder")`, `account_balances()["by_holder"]`), para o bot saber quem fala e para tratar Pix entre pessoas da família como `Transfer`.

- **`financial/`** — Main business logic:
  - `Transaction` — Income/expense with `confirmed` flag, linked to Category, PaymentMethod, optional Entity/Recurrence/Purchase
  - `Purchase` — Installment purchases. `save()` auto-generates `Installment` objects on creation via `generate_installments()`
  - `Installment` — Individual payment with `paid` flag, `reference_month`/`reference_year` for invoice grouping
  - `Recurrence` — Scheduled transaction templates (WEEKLY/MONTHLY/YEARLY/CUSTOM)
  - `DashboardView` — Aggregated financial summary at `/`
  - `InvoiceForecastView` — Invoices by due month and main card at `/previsao-faturas/` (installments, one-off credit purchases, refunds and card recurrences, via `financial/forecast.py`)
  - `Transfer` — Invoice payments and moves between own accounts/pots (not income or expense)

- **`assistant/`** — Assistente de IA independente de canal:
  - `agent.py` — `run_turn(chat_id, parts)`: loop manual modelo ↔ ferramentas, persiste cada passo em `ChatMessage` (formato nativo do provedor; histórico só cresce). Conversa nova por inatividade (`ASSISTANT_IDLE_HOURS`), `/novo`, ou mudança de provedor/modelo/prompt/ferramentas (`Conversation.prompt_hash`). Data/hora e avisos entram como mensagem `role: "system"` no meio da conversa.
  - `prompts.py` — system prompt congelado (sem dados dinâmicos; mudar aqui abre conversas novas).
  - `providers/` — protocolo `LLMProvider`, escolhido por `AI_PROVIDER`: `anthropic_provider.py` (padrão; stream + `get_final_message`, effort, cache, `fallbacks="default"`, Files API para PDF/imagem) e `openai_provider.py` (Chat Completions + function calling). Ferramentas SEM `strict` (o schema de `stage_entries` estoura o limite de gramática da Anthropic); toda entrada é validada com pydantic (`ToolInput`, `extra="forbid"`).
  - `tools/` — conjunto FIXO: consultas (`get_reference_data`, `query_transactions`, `spending_summary`, `get_invoice_forecast`, `get_account_balances`, `get_cash_flow_forecast`) e staging (`stage_entries`, `edit_staged_entries`, `present_batch`, `get_batch`), família (`save_family_member`, `assign_holder`), terceiros (`get_third_party_balances`, `mark_third_party`) e regras (`save_user_rule`). Só família, `mark_third_party` e `save_user_rule` gravam direto, e nenhuma cria ou altera valores: só dizem quem é quem, de quem é uma compra já gravada e que regra o usuário ditou. A IA **nunca grava** registros financeiros: só monta `ImportBatch`/`StagedEntry` (tipos EXPENSE, INCOME, REFUND, INSTALLMENT_PURCHASE, INSTALLMENT_CHARGE, TRANSFER). O lote também pode propor cadastros, aplicados só na confirmação: cartão principal (`new_payment_method`), outros cartões da mesma fatura (`additional_new_cards` + `payment_method_name` no item), ligação de cartões já cadastrados ao principal (`link_existing_card_ids`, aplicada na confirmação e desfeita no `undo`), caixinhas (`from_account_name`/`to_account_name`) e saldos (`balance_*`, `other_balances`). Conferências no resumo: soma da fatura, subtotal por cartão (`by_card`) e saldo do extrato (`opening_balance` + linhas = saldo final).
  - `dedup.py` — marca itens já registrados (valor/data/método ou conta; parcelas k/N contra `Installment`; `external_id` estável por linha de fatura ou FITID de OFX; transferências) e detecta parcelas antecipadas (várias parcelas da mesma compra na mesma fatura viram despesas simples).
  - `batch_service.py` — `commit` (só pelo botão Confirmar; trava por update condicional + `version`), `discard`, `undo` (`/desfazer`; restaura parcelas pagas, snapshots e cartão criado). Lançamentos de fatura gravam `Transaction.invoice_month`; duplicados existentes recebem o mês da fatura.
  - `extraction.py` — leitura de documentos (PDF/CSV/OFX) em **chamada única, sem ferramentas**, por um modelo mais barato que o do agente (`ANTHROPIC_EXTRACTION_MODEL`, padrão Sonnet 5.5; Haiku 5.5 é ~15x mais barato, com pequenos desvios): o pedido leva o documento + cadastros e volta o lote inteiro em JSON (`ExtractionOutput`, mesmo formato de `stage_entries`, mais `source_text` por item). O servidor confere antes de apresentar: soma da fatura, saldo do extrato e conferência linha a linha (`evidence_problems`: parcela lançada como compra à vista, sinal, valor). Se falhar: nova tentativa com o mesmo modelo → `ANTHROPIC_EXTRACTION_FALLBACK_MODEL` (Opus 5.5) → agente interativo. `ASSISTANT_DOCUMENT_MODE`: `batch` (API de batches, metade do preço; o worker consulta `poll()` a cada 20s), `direct` (na hora; também com a legenda "agora") ou `agent` (fluxo antigo). `ExtractionJob` guarda cada tentativa e o uso de tokens. Fotos e texto continuam no agente.
  - `costs.py` — gasto com IA: converte `ChatMessage.usage` e `ExtractionJob.usage` em dólares (tabela `DEFAULT_PRICES`, batch pela metade), `month_spend`, `over_limit` (o bot para de chamar a IA ao atingir `AI_MONTHLY_LIMIT_USD`) e `send_alerts` (e-mail aos 80%/100% de `AI_MONTHLY_BUDGET_USD` e no teto, uma vez por nível e por mês, via `SpendAlert`).
  - `UserRule` — regras permanentes ditas pelo usuário; entram em `get_reference_data` (`user_rules`) e por isso chegam ao agente e ao extrator.
  - `documents.py` — PDF (com senha: tenta `PDF_PASSWORDS`, senão pede ao usuário e apaga a mensagem), imagens, CSV/OFX; arquivos em `ASSISTANT_STORAGE_DIR` (fora de `MEDIA_ROOT`).

- **`telegram_bot/`** — Transporte Telegram:
  - `views.py` — webhook `/telegram/webhook/<secret>/` (`@login_not_required`): valida o secret do path e o header `X-Telegram-Bot-Api-Secret-Token`, grava `TelegramUpdate` (dedup por `update_id`) e responde 200. Botões de lote (`b:c|d|v:<id>:<version>`) são tratados na hora.
  - `bot.py` — `ingest_update` e `process_chat_updates` (comandos, anexos, senha de PDF, chama o agente, envia o resumo do lote com botões).
  - `management/commands/run_telegram_worker.py` — consome a fila, um chat por vez, juntando mensagens próximas (álbuns, arquivo + texto).
  - `digests.py` + `send_digests` — avisos sem IA (fatura vencendo, saldo projetado negativo, resumo mensal), sem repetir (`DigestLog`).
  - `client.py` — chamadas HTTP à Bot API; texto do modelo vai sem `parse_mode`; `is_allowed` nega tudo se `TELEGRAM_ALLOWED_CHAT_IDS` estiver vazio.
  - `render.py` — resumo/itens do lote. Comandos sem IA em `bot.py`: `/novo`, `/desfazer`, `/terceiros`, `/custo`, `/cancelar`, `/ajuda`. O fluxo antigo de comprovantes (`PendingTransaction`) foi removido; botões de mensagens antigas só recebem um aviso.
  - Env vars: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_WEBHOOK_SECRET`, `TELEGRAM_ALLOWED_CHAT_IDS`, `AI_PROVIDER` (`anthropic`|`openai`), `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL` (padrão `claude-opus-5-5`), `ANTHROPIC_EFFORT` (padrão `medium`), `ASSISTANT_DOCUMENT_MODE`, `ANTHROPIC_EXTRACTION_MODEL`, `ANTHROPIC_EXTRACTION_FALLBACK_MODEL`, `ANTHROPIC_EXTRACTION_EFFORT`, `OPENAI_API_KEY`, `OPENAI_MODEL`, `PDF_PASSWORDS`, `ASSISTANT_STORAGE_DIR`, `ASSISTANT_IDLE_HOURS`, `ASSISTANT_MAX_STEPS`, `CACHE_DIR`, `AI_MONTHLY_BUDGET_USD`, `AI_MONTHLY_LIMIT_USD`, `AI_PRICES_JSON`, `ALERT_EMAIL`, `EMAIL_HOST`/`EMAIL_PORT`/`EMAIL_USE_TLS`/`EMAIL_HOST_USER`/`EMAIL_HOST_PASSWORD`/`DEFAULT_FROM_EMAIL`, `BACKUP_DIR`.

- **`financial/forecast.py`** — funções puras usadas pelo bot e pelas views (Dashboard, Previsão de Faturas, Relatório Mensal): `invoice_period_for` (fechamento/vencimento do cartão; sem `closing_day` mantém o comportamento antigo), `transaction_invoice_period` (usa `Transaction.invoice_month` quando a compra veio de uma fatura importada), `recurrence_occurrences`, `projected_recurrences`, `invoice_forecast` (parcelas + compras à vista no crédito − estornos + recorrências no cartão; só o que falta pagar, salvo `include_paid`), `account_balances` (último `BalanceSnapshot`/saldo inicial + movimentos; cartão de crédito não entra), `monthly_cash_flow`, `spending_summary`. Mês de referência da fatura = mês do vencimento.
  - `InvoiceClosing` — fechamento/vencimento REAIS de cada fatura (cartão principal + mês de vencimento), gravados ao confirmar uma fatura importada (e desfeitos no `undo`). `invoice_period_for(pm, d, closings=None)` usa o `closing_day` como estimativa e, onde há fechamento real conhecido, desloca a compra para a fatura certa (`load_closings()` pré-carrega para laços). Não há projeção do padrão de meses anteriores: meses sem fatura importada usam só a estimativa.
  - `Transfer` (pagamento de fatura / transferência entre contas) é um modelo separado de `Transaction` de propósito; pagar uma fatura marca as parcelas daquele cartão/mês como pagas. `Purchase.generate_installments()` arredonda centavos e preserva `paid` ao regenerar.

- **Cartão emprestado (terceiros)** — `Transaction.on_behalf_of` / `Purchase.on_behalf_of` apontam para um `core.Entity` (tipo `PERSON`) de fora da família. A compra continua na fatura, na previsão e no saldo, mas fica fora dos gastos (`spending_summary(third_party="exclude")`, Dashboard, Relatório Mensal); receita com `on_behalf_of` é devolução (categoria "Devoluções de terceiros"), fora da receita. `forecast.third_party_balances()` dá a conta corrente por pessoa (gasto, vencido até o mês atual, futuro, devolvido). `PaymentMethod.lent_to` marca um cartão que fica com a pessoa (os itens importados nele já nascem atribuídos). No lote: `StagedEntry.on_behalf_of(_name)`; marcar um item já registrado grava a pessoa no lançamento/compra existente na confirmação (`batch_service._mark_existing_third_party`, desfeito no `undo`). Não há vínculo entre devolução e compra específica, de propósito.

- **Avisos e backup** — `core/alerts.py` (`send_alert`: e-mail para `ALERT_EMAIL`; sem `EMAIL_HOST` vai para o console) e `core/management/commands/backup_data.py` (pg_dump ou cópia do SQLite + tar dos arquivos do bot, verificação, retenção, e-mail em caso de falha).

- **Login** — `LoginRequiredMiddleware` protege todo o site (`/entrar/`, `/sair/`); só o webhook é isento.

### View Pattern

All CRUD views follow the same pattern (mixins in `core/mixins.py`):
- **List**: `FilterView` (django-filter) with 20/page pagination. Returns `*_table.html` partial for HTMX, full `*_list.html` otherwise. The table partial also re-renders the band numbers out-of-band (`_*_stats.html` with `hx-swap-oob`) so totals follow the filters.
- **Create/Update** (`HtmxModalFormMixin`): form opens in `#modal-container`; on HTMX submit returns the table partial with `HX-Trigger` (event + `showToast`). Invalid forms come back into the modal (`HX-Retarget`). Opened outside its list (`?depois=recarregar`, e.g. "Nova transação" in the top bar), it saves and sends `HX-Refresh`, with the toast carried by Django messages.
- **Delete** (`HtmxDeleteMixin`): `DELETE` via the shared confirm dialog (`data-delete`, `data-target`); returns the table partial. A `ProtectedError` returns 409 with an error toast instead of a 500.
- **Inline creation**: Category, Tag, Entity, and PaymentMethod support `?inline` POST with JSON body (Alpine `inlineCreate` in `static/js/confin.js`).

### URL Namespacing

- `financial:` — dashboard (`/`, `?mes=AAAA-MM`), transactions (`/transacoes/`), purchases (`/compras/`), recurrences (`/recorrencias/`), transfers (`/transferencias/`), invoice forecast (`/previsao-faturas/`), cards and real closings (`/cartoes/`), third parties (`/terceiros/`), monthly report (`/relatorios/mensal/`)
- `accounts:` — accounts and pots with balances (`/contas/`), balance snapshots (`/saldos/informar/`, `/contas/<pk>/saldos/`), payment methods
- `core:` — categories, tags, entities, family (`/familia/`)
- `assistant:` — bot batches (`/assistente/lotes/`; the detail page confirms, discards and undoes through `batch_service.commit/discard/undo`, the same rules as the bot: version check, and only the chat's last confirmed batch can be undone; it leaves a note for the agent and edits the Telegram summary), user rules (`/assistente/regras/`), AI spend (`/assistente/custo/`)
- URLs use Portuguese paths (e.g., `/transacoes/criar/`, `/compras/<pk>/editar/`)

### Frontend

Design context lives in `PRODUCT.md` (product truth) and `.impeccable/surfaces/` (direction contract); `DESIGN.md` documents the visual system.
- **Design system**: `static/css/confin.css` (tokens for light and dark, components) and `static/js/confin.js` (theme, toasts, modal, confirm dialog, nav menus, Select2 setup, Alpine components). Signature: every screen opens with `.band`, a solid cobalt field with 2-4 numbers and an optional proportion bar (`.prop`).
- **Widgets**: forms and filters use `core/widgets.py` (`field` class for inputs/selects/textareas, `check` for checkboxes); `FriendlyEmptyLabels` replaces the `---------` empty choice.
- **Template tags**: `{% load ui %}` gives `brl`/`rs`/`signed` (Brazilian money format), `icon` (Lucide paths), `pct`, `month_name`, `ym_label`, `nav_active`, `query_with`, `active_count`.
- **Templates**: `templates/base.html` (top bar with grouped menus, mobile bottom bar and menu sheet), `templates/layouts/list.html` (band + filters + table), `templates/partials/` (field, modal, form modal, pagination, row actions). Tables use `rtable` with `c-main`/`c-amount`/`c-meta`/`c-hide`/`c-actions` cells so they turn into stacked rows on phones.
- **HTMX** for partial page updates; **Select2** only on desktop and for multi-selects (phones keep native selects).

### Key Conventions

- All model field labels use `gettext_lazy` (Portuguese, `LANGUAGE_CODE = 'pt-br'`)
- Monetary fields: `DecimalField(max_digits=12, decimal_places=2)` with `MinValueValidator(0.01)`
- Foreign keys to reference data use `on_delete=models.PROTECT`
- Soft deletes via `active` boolean on reference models (Category, Tag, Entity, BankAccount, PaymentMethod)
- `created_at` (auto_now_add) / `updated_at` (auto_now) on all models
- `USE_TZ = False`, timezone `America/Belem`
- Environment variables from `.env` via python-dotenv
