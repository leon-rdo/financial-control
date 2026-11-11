# To Do

## Feito

- [x] Autenticação nas views (login obrigatório em todo o site; só o webhook do Telegram é isento)
- [x] Cadastro de ID do Telegram (pessoas da família ligadas ao chat; o bot sabe quem está falando)

## A decidir

- RLS, compartilhamento entre usuários e permissões de CRUD: a decisão atual é finanças em conjunto (todos da família veem tudo). Estes itens só voltam a fazer sentido se o app passar a atender mais de uma família.
- Compras de terceiros no cartão emprestado: proposta de marcar a compra com a pessoa e manter uma conta corrente por pessoa (quanto deve, quanto já devolveu), sem contar como gasto nem como receita da família.

## Operação

- [ ] Backup do banco de produção e dos arquivos recebidos pelo bot
- [ ] Aviso quando o worker do bot cair, uma mensagem falhar ou uma leitura em batch ficar presa
- [ ] Teto ou alerta de gasto com a API e um comando `/custo` (os tokens já ficam gravados em `ChatMessage.usage` e `ExtractionJob.usage`)
- [ ] Bot de desenvolvimento separado (hoje `run_telegram_worker --poll` exige remover o webhook de produção)

## Produto

- [ ] Telas no site para transferências, saldos informados, caixinhas e pessoas da família (hoje só no admin)
- [ ] Dividir um item entre a família e outra pessoa
- [ ] Memória de categorias a partir das correções do usuário
- [ ] Sugerir recorrências a partir de cobranças que se repetem
- [ ] Orçamento por categoria e metas para caixinhas
- [ ] Receber faturas por e-mail
- [ ] Recuperação de senha no site

## Código

- [ ] Remover o fluxo antigo de comprovantes (`telegram_bot/handlers.py`, `ai_service.py`, `matching.py`, `transaction_service.py`, `keyboards.py`, `PendingTransaction`) quando não houver mais mensagens antigas com botões
- [ ] Consertar ou remover `accounts/management/commands/import_csv.py` (usa modelos que não existem mais)
- [ ] Apagar da OpenAI os arquivos enviados quando `AI_PROVIDER=openai` (na Anthropic eles expiram em 7 dias)

## Ainda não testado com dados reais

- [ ] Mensagem real pelo Telegram em produção, incluindo um documento lido em batch
- [ ] Foto de comprovante, PDF com senha de banco, extrato em OFX ou CSV
- [ ] Extrato do segundo cônjuge (o mesmo Pix visto dos dois lados)
- [ ] Fatura inteira com `AI_PROVIDER=openai`
