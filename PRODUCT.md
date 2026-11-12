# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Uma família (hoje um casal) com finanças conjuntas, no Brasil. Todos veem e editam tudo; o titular de cada conta ou cartão serve só para relatórios por pessoa. O lançamento do dia a dia vai pelo bot do Telegram; o site é usado no computador e no celular por igual, para quatro trabalhos de mesmo peso:

- **Planejar o futuro:** quanto vem de fatura em cada mês, saldo previsto, parcelas que terminam.
- **Entender os gastos:** para onde foi o dinheiro, por categoria, entre meses e por pessoa.
- **Lançar e cadastrar à mão:** transações, parcelados, recorrências, contas, cartões, categorias.
- **Conferir e corrigir:** revisar o que o bot gravou, achar erro, editar ou excluir.

## Product Purpose

Controle financeiro pessoal e familiar: despesas, receitas, compras parceladas, recorrências, faturas de cartão, contas e caixinhas. O sucesso é a família saber, sem planilha, quanto tem, quanto vai sair e para onde foi o dinheiro, com números que batem com o banco.

## Positioning

O bot lê faturas, extratos e comprovantes e monta um lote; nada é gravado sem a confirmação de uma pessoa, e todo lote pode ser desfeito. A previsão de faturas usa o fechamento real de cada fatura importada, o mês da fatura é o mês do vencimento, cartões adicionais caem na fatura do principal, e compras feitas por pessoas de fora da família no cartão emprestado ficam na fatura mas fora dos gastos da família.

## Operating Context

- Vocabulário bancário brasileiro: fatura, fechamento, vencimento, parcela 3/10, à vista, estorno, Pix, boleto, débito, extrato, OFX, caixinha/cofrinho, cartão adicional e virtual, "cobrado na fatura de".
- Ritmo mensal: faturas fecham e vencem; avisos automáticos às 8h; documentos importados um mês por vez, do mais antigo para o mais novo.
- Volume real em produção: cerca de 1.500 lançamentos, 500 transferências, 13 contas e caixinhas, 14 cartões. Listas precisam de paginação e leitura rápida.
- Valores em reais (R$), datas dd/mm/aaaa, interface toda em português.

## Capabilities and Constraints

- Django com templates no servidor, HTMX para atualizações parciais, Alpine.js, Select2 nos campos de escolha. Listas com 20 por página e partial `*_table.html`; formulários em modal que devolvem a tabela com `HX-Trigger`.
- Login obrigatório em todo o site.
- A IA nunca grava registros financeiros: só monta lotes, e quem confirma é uma pessoa.
- Totais devem vir das funções de `financial/forecast.py`, para bater com o bot.
- O repositório é público: nomes reais, finais de cartão, CPF/CNPJ e chat IDs nunca entram no código nem em exemplos.
- Telas ainda inexistentes no site (hoje só no bot e no admin): fechamentos e cartões ligados, transferências, saldos informados, caixinhas, pessoas da família, compras de terceiros, regras do usuário, gasto com IA, lotes de importação.

## Brand Commitments

- Nome: **Confin** (domínio confin.site). O nome antigo "Controle Financeiro" e o logo da carteira podem sair.
- Voz: português simples e direto, como em `docs/GUIA.md`: frases curtas, verbos claros, sem jargão de sistema.
- Preferência declarada (novembro de 2026): o visual familiar de painel de controle financeiro, o padrão da categoria, com um detalhe próprio. Entre propostas mais ousadas e variações do padrão, a família escolheu a variação do padrão.

## Evidence on Hand

- Dados reais só no servidor de produção; o banco local tem poucos registros. Qualquer dado de demonstração é sintético e não deve imitar pessoas reais.
- Guia de uso: `docs/GUIA.md`. Pendências de produto: `TODO.md`.

## Product Principles

1. **Os números batem.** Com o banco, com o bot e entre telas; um total que diverge é pior que um total ausente.
2. **O futuro pesa tanto quanto o passado.** O que vai vencer fica tão visível quanto o que já aconteceu.
3. **A pessoa confere, o sistema propõe.** Nada é gravado sem alguém ver; corrigir precisa ser rápido.
4. **Família junta.** Sem permissões por pessoa; o titular é uma lente de leitura, não uma barreira.
5. **Muitos dados, pouca cerimônia.** Densidade e leitura rápida valem mais que decoração.
