# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**financial-control** is a Django-based personal finance management application for tracking expenses, income, installment-based purchases, and recurrences. Built with Django 6+, HTMX for dynamic UI, Tailwind CSS + DaisyUI components, and Select2 for enhanced dropdowns.

## Commands

```bash
source .venv/bin/activate          # Python 3.12 venv
uv pip install -e .                # Install deps via uv

python manage.py runserver         # Dev server on :8000
python manage.py makemigrations    # After model changes
python manage.py migrate           # Apply migrations
python manage.py import_csv <csv>  # Import financial data from CSV

# Telegram bot: webhook só enfileira; o worker processa (IA)
python manage.py setup_telegram_webhook --url <public_url>/telegram/webhook/<TELEGRAM_WEBHOOK_SECRET>/
python manage.py setup_telegram_webhook --delete  # Remove webhook
python manage.py run_telegram_worker              # Worker (produção, junto com o webhook)
python manage.py run_telegram_worker --poll       # Dev local sem URL pública (exige webhook removido)

python manage.py send_digests [--dry-run] [--date AAAA-MM-DD]  # Avisos automáticos (1x/dia)

python manage.py test financial assistant telegram_bot  # Testes (Django TestCase)

deploy/deploy.sh                   # Publica em produção (confin.site, host ssh leonardo_contabo)
```

No linter is configured. `uv sync --no-install-project` instala a partir do `uv.lock` (extra `prod` = gunicorn + psycopg).

## Production

`https://confin.site` em `/var/www/confin` (host ssh `leonardo_contabo`): nginx → gunicorn `confin.service` (127.0.0.1:8030), `confin-worker.service` (bot), `confin-digests.timer` (8h de Brasília), PostgreSQL local (`DB_USED=postgres`). Segredos só no `.env` do servidor. Arquivos em `deploy/`; `deploy/deploy.sh` faz rsync + `uv sync` + `migrate` + `collectstatic` + restart. Logs: `journalctl -u confin -u confin-worker -f`.

## Architecture

### Django Project: `financial_control/`

Settings in `financial_control/settings.py`. Database defaults to SQLite; set `DB_USED=mysql` env var to switch. Root URL conf mounts apps at `/` (core, accounts, financial) and `/telegram/` (telegram_bot).

### Apps

- **`core/`** — Reference data: `Category` (INCOME/EXPENSE/BOTH), `Tag`, `Entity` (SUPPLIER/EMPLOYER/CLIENT/OTHER). Has CNPJ lookup API (`fetch_cnpj_data`). Contains `HTMXMiddleware` (`core/middleware.py`) that sets `request.htmx` boolean from `HX-Request` header.

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
  - `InvoiceForecastView` — Groups unpaid installments by month and payment method at `/previsao-faturas/`

- **`assistant/`** — Assistente de IA independente de canal:
  - `agent.py` — `run_turn(chat_id, parts)`: loop manual modelo ↔ ferramentas, persiste cada passo em `ChatMessage` (formato nativo do provedor; histórico só cresce). Conversa nova por inatividade (`ASSISTANT_IDLE_HOURS`), `/novo`, ou mudança de provedor/modelo/prompt/ferramentas (`Conversation.prompt_hash`). Data/hora e avisos entram como mensagem `role: "system"` no meio da conversa.
  - `prompts.py` — system prompt congelado (sem dados dinâmicos; mudar aqui abre conversas novas).
  - `providers/` — protocolo `LLMProvider`, escolhido por `AI_PROVIDER`: `anthropic_provider.py` (padrão; stream + `get_final_message`, effort, cache, `fallbacks="default"`, Files API para PDF/imagem) e `openai_provider.py` (Chat Completions + function calling). Ferramentas SEM `strict` (o schema de `stage_entries` estoura o limite de gramática da Anthropic); toda entrada é validada com pydantic (`ToolInput`, `extra="forbid"`).
  - `tools/` — conjunto FIXO: consultas (`get_reference_data`, `query_transactions`, `spending_summary`, `get_invoice_forecast`, `get_account_balances`, `get_cash_flow_forecast`) e staging (`stage_entries`, `edit_staged_entries`, `present_batch`, `get_batch`) e família (`save_family_member`, `assign_holder`: únicas que gravam direto, só cadastro de quem é quem). A IA **nunca grava** registros financeiros: só monta `ImportBatch`/`StagedEntry` (tipos EXPENSE, INCOME, REFUND, INSTALLMENT_PURCHASE, INSTALLMENT_CHARGE, TRANSFER). O lote também pode propor cadastros, aplicados só na confirmação: cartão principal (`new_payment_method`), outros cartões da mesma fatura (`additional_new_cards` + `payment_method_name` no item), caixinhas (`from_account_name`/`to_account_name`) e saldos (`balance_*`, `other_balances`). Conferências no resumo: soma da fatura, subtotal por cartão (`by_card`) e saldo do extrato (`opening_balance` + linhas = saldo final).
  - `dedup.py` — marca itens já registrados (valor/data/método ou conta; parcelas k/N contra `Installment`; `external_id` estável por linha de fatura ou FITID de OFX; transferências) e detecta parcelas antecipadas (várias parcelas da mesma compra na mesma fatura viram despesas simples).
  - `batch_service.py` — `commit` (só pelo botão Confirmar; trava por update condicional + `version`), `discard`, `undo` (`/desfazer`; restaura parcelas pagas, snapshots e cartão criado). Lançamentos de fatura gravam `Transaction.invoice_month`; duplicados existentes recebem o mês da fatura.
  - `extraction.py` — leitura de documentos (PDF/CSV/OFX) em **chamada única, sem ferramentas**, por um modelo mais barato que o do agente (`ANTHROPIC_EXTRACTION_MODEL`, padrão Sonnet 5.5; Haiku 5.5 é ~15x mais barato, com pequenos desvios): o pedido leva o documento + cadastros e volta o lote inteiro em JSON (`ExtractionOutput`, mesmo formato de `stage_entries`, mais `source_text` por item). O servidor confere antes de apresentar: soma da fatura, saldo do extrato e conferência linha a linha (`evidence_problems`: parcela lançada como compra à vista, sinal, valor). Se falhar: nova tentativa com o mesmo modelo → `ANTHROPIC_EXTRACTION_FALLBACK_MODEL` (Opus 5.5) → agente interativo. `ASSISTANT_DOCUMENT_MODE`: `batch` (API de batches, metade do preço; o worker consulta `poll()` a cada 20s), `direct` (na hora; também com a legenda "agora") ou `agent` (fluxo antigo). `ExtractionJob` guarda cada tentativa e o uso de tokens. Fotos e texto continuam no agente.
  - `documents.py` — PDF (com senha: tenta `PDF_PASSWORDS`, senão pede ao usuário e apaga a mensagem), imagens, CSV/OFX; arquivos em `ASSISTANT_STORAGE_DIR` (fora de `MEDIA_ROOT`).

- **`telegram_bot/`** — Transporte Telegram:
  - `views.py` — webhook `/telegram/webhook/<secret>/` (`@login_not_required`): valida o secret do path e o header `X-Telegram-Bot-Api-Secret-Token`, grava `TelegramUpdate` (dedup por `update_id`) e responde 200. Botões de lote (`b:c|d|v:<id>:<version>`) são tratados na hora.
  - `bot.py` — `ingest_update` e `process_chat_updates` (comandos, anexos, senha de PDF, chama o agente, envia o resumo do lote com botões).
  - `management/commands/run_telegram_worker.py` — consome a fila, um chat por vez, juntando mensagens próximas (álbuns, arquivo + texto).
  - `digests.py` + `send_digests` — avisos sem IA (fatura vencendo, saldo projetado negativo, resumo mensal), sem repetir (`DigestLog`).
  - `client.py` — chamadas HTTP à Bot API; texto do modelo vai sem `parse_mode`; `is_allowed` nega tudo se `TELEGRAM_ALLOWED_CHAT_IDS` estiver vazio.
  - `render.py` — resumo/itens do lote. `handlers.py`, `ai_service.py`, `matching.py`, `transaction_service.py`, `keyboards.py` = fluxo antigo de `PendingTransaction` (só atende botões de mensagens antigas).
  - Env vars: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_WEBHOOK_SECRET`, `TELEGRAM_ALLOWED_CHAT_IDS`, `AI_PROVIDER` (`anthropic`|`openai`), `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL` (padrão `claude-opus-5-5`), `ANTHROPIC_EFFORT` (padrão `medium`), `ASSISTANT_DOCUMENT_MODE`, `ANTHROPIC_EXTRACTION_MODEL`, `ANTHROPIC_EXTRACTION_FALLBACK_MODEL`, `ANTHROPIC_EXTRACTION_EFFORT`, `OPENAI_API_KEY`, `OPENAI_MODEL`, `PDF_PASSWORDS`, `ASSISTANT_STORAGE_DIR`, `ASSISTANT_IDLE_HOURS`, `ASSISTANT_MAX_STEPS`, `CACHE_DIR`.

- **`financial/forecast.py`** — funções puras usadas pelo bot e pelas views (Dashboard, Previsão de Faturas, Relatório Mensal): `invoice_period_for` (fechamento/vencimento do cartão; sem `closing_day` mantém o comportamento antigo), `transaction_invoice_period` (usa `Transaction.invoice_month` quando a compra veio de uma fatura importada), `recurrence_occurrences`, `projected_recurrences`, `invoice_forecast` (parcelas + compras à vista no crédito − estornos + recorrências no cartão; só o que falta pagar, salvo `include_paid`), `account_balances` (último `BalanceSnapshot`/saldo inicial + movimentos; cartão de crédito não entra), `monthly_cash_flow`, `spending_summary`. Mês de referência da fatura = mês do vencimento.
  - `Transfer` (pagamento de fatura / transferência entre contas) é um modelo separado de `Transaction` de propósito; pagar uma fatura marca as parcelas daquele cartão/mês como pagas. `Purchase.generate_installments()` arredonda centavos e preserva `paid` ao regenerar.

- **Login** — `LoginRequiredMiddleware` protege todo o site (`/entrar/`, `/sair/`); só o webhook é isento.

### View Pattern

All CRUD views follow the same pattern:
- **List**: `FilterView` (django-filter) with 20/page pagination. Returns `*_table.html` partial for HTMX, full `*_list.html` otherwise.
- **Create/Update**: ModelForm-based. On HTMX submit, returns table HTML with `HX-Trigger` header instead of redirect.
- **Delete**: Same HTMX pattern — returns updated table partial or normal redirect.
- **Inline creation**: Category, Tag, Entity, and PaymentMethod support `?inline` POST with JSON body for creating records from within other forms.

### URL Namespacing

- `financial:` — dashboard (`/`), transactions (`/transacoes/`), purchases (`/compras/`), recurrences (`/recorrencias/`), invoice forecast (`/previsao-faturas/`)
- `accounts:` — bank accounts, payment methods
- `core:` — categories, tags, entities
- URLs use Portuguese paths (e.g., `/transacoes/criar/`, `/compras/<pk>/editar/`)

### Frontend

- **Tailwind CSS + DaisyUI** classes (`input input-bordered`, `select select-bordered`, `btn`, etc.)
- **HTMX** for partial page updates — list views serve `*_table.html` partials, forms trigger refreshes via HX-Trigger events
- **Select2** for dropdown fields (django-select2)
- **Templates**: `templates/base.html` (shared layout), then `<app>/templates/<app>/` per app. Each list page has a `*_table.html` partial for HTMX responses.
- Filter widgets apply DaisyUI CSS classes directly in FilterSet definitions

### Key Conventions

- All model field labels use `gettext_lazy` (Portuguese, `LANGUAGE_CODE = 'pt-br'`)
- Monetary fields: `DecimalField(max_digits=12, decimal_places=2)` with `MinValueValidator(0.01)`
- Foreign keys to reference data use `on_delete=models.PROTECT`
- Soft deletes via `active` boolean on reference models (Category, Tag, Entity, BankAccount, PaymentMethod)
- `created_at` (auto_now_add) / `updated_at` (auto_now) on all models
- `USE_TZ = False`, timezone `America/Belem`
- Environment variables from `.env` via python-dotenv
