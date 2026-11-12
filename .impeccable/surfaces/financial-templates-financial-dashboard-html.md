---
version: 1
slug: "financial-templates-financial-dashboard-html"
primary_target: "financial/templates/financial/dashboard.html"
related_targets: ["templates/base.html"]
---

# Confin, app inteiro (painel e todas as telas)

Mode: Operate. Escopo: redesign completo das telas existentes e criação das telas que só existiam no bot e no admin (transferências, contas e caixinhas com saldos, cartões e fechamentos, terceiros, família, lotes do bot, regras, gasto com IA). Usado no computador e no celular por igual.

Tarefa da primeira tela: responder "como está o mês" (entrou, saiu, sobra), depois o que vence e os últimos lançamentos. Evitar: cara de app de banco, números escondidos, tela ruim no celular.

## Direction contract

THESIS: O painel de controle financeiro que a família já conhece, com uma ideia própria: cada tela abre com uma faixa de cor chapada que traz os números que importam e uma barra de proporção. Recusa cards de KPI coloridos com gráficos de enfeite e a planilha cinza sem hierarquia.

OWN-WORLD: Identidade modernista brasileira dos anos 60 e 70. Azul cobalto #1B3F8F em campo chapado, branco, fundo #F2F4F8, tinta #14213D, amarelo #F2B705 só como acento (sobra, marca, seleção). Verde #17804A para entrada, vermelho #C62828 para alerta. Manrope em todo lugar, números tabulares. Cartões brancos com borda fina de 1px e raio 10px, sem sombra. Grade rígida de 12 colunas.

STORY: A pessoa abre e entende o mês em três números e uma barra; vê o que vence e se algo atrasou; corrige ou lança em um clique. Nas outras telas, a faixa resume a lista (total filtrado, a pagar, disponível) antes da tabela.

FIRST VIEWPORT: Barra superior branca de 58px: marca à esquerda, grupos de navegação (Painel, Lançamentos, Cartões, Dinheiro, Análise, Assistente, Cadastros) e "Nova transação" à direita. Faixa azul de ponta a ponta: mês e navegação entre meses, quatro números brancos de 38px (Entrou, Saiu, Sobra, Disponível) e a barra de proporção entrou/saiu com legenda. Abaixo, três colunas: Para onde foi (barras na cor da categoria), Vem aí (dia em bloco, vencido em vermelho), Últimos lançamentos. No celular: faixa com os números empilhados 2x2, colunas viram seções, barra inferior com Painel, Lançamentos, Faturas, Contas e Menu.

FORM: Padrão com faixa modernista, candidato da rodada conservadora (registro safer, escolhido pelo usuário entre três variações do padrão da categoria). seed:3be51e4855c14153

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance

## Assinatura

A faixa (classe `.band`): campo azul chapado no topo de cada tela com 2 a 4 números da tela e, quando houver uma relação parte/todo, uma barra de proporção. Uma por tela, sempre a primeira coisa do conteúdo.

## Em aberto

- Lotes do bot ficam só leitura nesta rodada (confirmar e desfazer continuam no Telegram).
