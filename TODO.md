# To Do

Revisado em 11/11/2026. O guia de uso está em [docs/GUIA.md](docs/GUIA.md).

## Feito

- [x] Autenticação nas views (login obrigatório em todo o site; só o webhook do Telegram é isento)
- [x] Cadastro de ID do Telegram (pessoas da família ligadas ao chat; o bot sabe quem está falando)
- [x] Cartão emprestado: compras de terceiros marcadas com a pessoa, fora dos gastos da família, com conta corrente por pessoa (`/terceiros`)
- [x] Regras permanentes ditas ao bot ("Pix para a minha empresa é gasto"), usadas nos próximos documentos
- [x] Backup diário do banco e dos arquivos recebidos pelo bot, com aviso por e-mail se falhar
- [x] Orçamento e teto mensal de gasto com IA, avisos por e-mail e comando `/custo`
- [x] Fluxo antigo de comprovantes (`PendingTransaction`) e `import_csv` removidos
- [x] Arquivos enviados à OpenAI passam a expirar sozinhos em 7 dias

## Retirado

- RLS, compartilhamento entre usuários e permissões de CRUD por usuário. A decisão foi finanças em conjunto: todos da família veem e editam tudo, e o titular de cada conta ou cartão serve para relatórios por pessoa. Estes itens só voltam se o app passar a atender mais de uma família.

## Operação

- [ ] Sentry: erros do site e do worker, e aviso quando o worker cair, uma mensagem falhar ou uma leitura em batch ficar presa (hoje só há e-mail para gasto com IA e falha de backup)
- [ ] Copiar os backups para fora do servidor (hoje ficam em `/var/backups/confin`, na mesma máquina)
- [ ] Criar o bot de desenvolvimento no BotFather e usar o token dele no `.env` local (passos no README)

## Produto

- [ ] Telas no site (sessão dedicada, ainda não começada): transferências, saldos informados, caixinhas, pessoas da família, compras de terceiros (campo "por conta de" nos formulários e quem deve quanto), regras do usuário e gasto com IA. Hoje tudo isso existe só no bot e no admin.
- [ ] Dividir um item entre a família e outra pessoa
- [ ] Sugerir recorrências a partir de cobranças que se repetem
- [ ] Orçamento por categoria e metas para caixinhas
- [ ] Receber faturas por e-mail
- [ ] Recuperação de senha no site (agora que o envio de e-mail está configurado)

## Código

- [ ] Traduzir em `locale/pt_BR` os rótulos novos dos modelos (titular, cobrado na fatura de, por conta de, emprestado a)
- [ ] Preços dos modelos da OpenAI em `AI_PRICES_JSON`, se `AI_PROVIDER=openai` for usado (sem isso essas chamadas ficam fora do total de `/custo`)

## Ainda não testado com dados reais

- [ ] Mensagem real pelo Telegram em produção, incluindo um documento lido em batch
- [ ] Foto de comprovante, PDF com senha de banco, extrato em OFX ou CSV
- [ ] Extrato do segundo cônjuge (o mesmo Pix visto dos dois lados)
- [ ] Fatura inteira com `AI_PROVIDER=openai`
- [ ] Fatura real com itens de terceiros e a devolução vinda no extrato
- [ ] Avisos diários em produção (ainda não há dados)
