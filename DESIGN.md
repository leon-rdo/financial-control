---
name: Confin
description: Controle financeiro da família, com uma faixa de cobalto chapado que abre cada tela com os números que importam.
colors:
  cobalt: "#1B3F8F"
  cobalt-deep: "#15336F"
  cobalt-tint: "#E8EEF9"
  sun-yellow: "#F2B705"
  page-mist: "#F2F4F8"
  surface: "#FFFFFF"
  surface-2: "#F6F7FA"
  ink: "#14213D"
  ink-2: "#33405C"
  mute: "#58627A"
  line: "#E0E4EC"
  line-2: "#EDF0F5"
  line-strong: "#C7CEDB"
  money-green: "#17804A"
  money-green-tint: "#E6F4EC"
  alert-red: "#C62828"
  alert-red-tint: "#FDECEC"
  pending-amber: "#9A5B00"
  pending-amber-tint: "#FFF3D6"
  night-band: "#1C3A80"
  night-bg: "#0F1526"
  night-surface: "#161E33"
  night-ink: "#E7EBF3"
  night-blue: "#7FA2EE"
typography:
  display:
    fontFamily: "Manrope, ui-sans-serif, system-ui, -apple-system, Segoe UI, sans-serif"
    fontSize: "38px"
    fontWeight: 800
    lineHeight: 1.1
    letterSpacing: "-0.02em"
    fontFeature: "\"tnum\" 1, \"lnum\" 1"
  headline:
    fontFamily: "Manrope, ui-sans-serif, system-ui, sans-serif"
    fontSize: "26px"
    fontWeight: 800
    lineHeight: 1.15
    letterSpacing: "-0.02em"
  title:
    fontFamily: "Manrope, ui-sans-serif, system-ui, sans-serif"
    fontSize: "16px"
    fontWeight: 800
    letterSpacing: "-0.01em"
  body:
    fontFamily: "Manrope, ui-sans-serif, system-ui, sans-serif"
    fontSize: "14px"
    fontWeight: 500
    lineHeight: 1.5
    fontFeature: "\"tnum\" 1, \"lnum\" 1"
  label:
    fontFamily: "Manrope, ui-sans-serif, system-ui, sans-serif"
    fontSize: "13px"
    fontWeight: 700
  meta:
    fontFamily: "Manrope, ui-sans-serif, system-ui, sans-serif"
    fontSize: "12px"
    fontWeight: 500
rounded:
  tag: "5px"
  badge: "6px"
  sm: "8px"
  md: "10px"
  lg: "12px"
  sheet: "16px"
spacing:
  xs: "8px"
  sm: "12px"
  md: "16px"
  lg: "20px"
  band: "26px"
  gutter: "40px"
components:
  button-primary:
    backgroundColor: "{colors.cobalt}"
    textColor: "{colors.surface}"
    rounded: "{rounded.sm}"
    padding: "0 14px"
    height: "36px"
  button-primary-hover:
    backgroundColor: "{colors.cobalt-deep}"
    textColor: "{colors.surface}"
  button-secondary:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.sm}"
    padding: "0 14px"
    height: "36px"
  button-ghost:
    backgroundColor: "transparent"
    textColor: "{colors.ink-2}"
    rounded: "{rounded.sm}"
    height: "36px"
  button-danger:
    backgroundColor: "{colors.alert-red}"
    textColor: "{colors.surface}"
    rounded: "{rounded.sm}"
    height: "36px"
  band-button:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.cobalt}"
    rounded: "{rounded.sm}"
    padding: "0 14px"
    height: "36px"
  band:
    backgroundColor: "{colors.cobalt}"
    textColor: "{colors.surface}"
    padding: "26px 40px"
  card:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.md}"
    padding: "18px 20px"
  field:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.sm}"
    padding: "0 12px"
    height: "38px"
  badge-blue:
    backgroundColor: "{colors.cobalt-tint}"
    textColor: "{colors.cobalt}"
    rounded: "{rounded.badge}"
    height: "22px"
  badge-green:
    backgroundColor: "{colors.money-green-tint}"
    textColor: "{colors.money-green}"
    rounded: "{rounded.badge}"
    height: "22px"
  badge-red:
    backgroundColor: "{colors.alert-red-tint}"
    textColor: "{colors.alert-red}"
    rounded: "{rounded.badge}"
    height: "22px"
  badge-amber:
    backgroundColor: "{colors.pending-amber-tint}"
    textColor: "{colors.pending-amber}"
    rounded: "{rounded.badge}"
    height: "22px"
  segment-on:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.surface}"
    rounded: "{rounded.sm}"
    height: "30px"
  toast:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.surface}"
    rounded: "{rounded.md}"
  topbar:
    backgroundColor: "{colors.surface}"
    height: "58px"
---

# Design System: Confin

## Overview

**Creative North Star: "O Cartaz do Mês"**

Confin é o painel financeiro que a família já conhece, com uma ideia própria tirada da identidade modernista brasileira dos anos 60 e 70: cada tela abre com um campo de cobalto chapado, de ponta a ponta, que traz os dois a quatro números daquela tela em branco grande e, quando existe uma relação parte/todo, uma barra de proporção branca e amarela. Abaixo da faixa, tudo é papel: fundo névoa, cartões brancos de borda fina, tabelas densas, tinta azul-marinho. A cor forte mora num lugar só; o resto é leitura.

A densidade é deliberada. São cerca de 1.500 lançamentos, 14 cartões e 13 contas; a interface prefere linhas de 44px, números tabulares alinhados à direita e meta-texto de 12px a respiros decorativos. Não há gráficos de enfeite, cards de KPI coloridos nem ilustrações. O mesmo sistema funciona no computador e no celular com o mesmo peso: no celular a faixa empilha os números 2x2, tabelas viram linhas empilhadas, modais viram folhas que sobem de baixo e a navegação desce para uma barra inferior.

O tema escuro é um par completo, não uma inversão: a faixa fica num cobalto mais fundo (night-band), as superfícies passam a azul-noite e o azul de ação clareia (night-blue), com texto escuro dentro do botão primário.

**Key Characteristics:**
- Uma faixa de cobalto chapado por tela, sempre o primeiro bloco do conteúdo.
- Manrope em todos os papéis, números tabulares e lineares no corpo inteiro.
- Superfícies planas com borda de 1px; sombra só no que flutua.
- Verde só para dinheiro que entra, vermelho só para alerta e negativo, despesa na cor da tinta.
- Amarelo como acento raro: sobra na barra de proporção, marca, seleção de texto.

## Colors

Um azul cobalto chapado, um amarelo de acento e uma escala de cinzas azulados frios; verde, vermelho e âmbar só como sinais.

### Primary
- **Cobalto Modernista** (cobalt): o campo da faixa, o botão primário, o sublinhado de navegação ativa, a cor de foco e de barras genéricas. No tema escuro a faixa usa **Cobalto Noturno** (night-band) e o azul de ação passa a **Azul Claro Noturno** (night-blue).
- **Cobalto Fundo** (cobalt-deep): hover do botão primário e do botão da faixa.
- **Névoa Cobalto** (cobalt-tint): fundo do item de menu ativo, do dia de hoje no bloco de data, de badges azuis e das escolhas no Select2 múltiplo.

### Secondary
- **Amarelo Sol** (sun-yellow): a parte "sobra" da barra de proporção, a barra direita da marca, o ícone de alerta dentro da faixa e a seleção de texto (a 38% de opacidade). Nunca preenche botão, fundo de cartão ou texto.

### Tertiary (sinais de dinheiro e estado)
- **Verde Entrada** (money-green) com seu fundo (money-green-tint): valores de receita (`+1.234,56`), a marca de estado confirmado, badges de "pago".
- **Vermelho Alerta** (alert-red) com seu fundo (alert-red-tint): vencido, atrasado, saldo negativo, erro de campo, botão de excluir. Dentro da faixa o negativo vira um rosa claro (#FFD3D3) para manter contraste sobre o cobalto.
- **Âmbar Pendente** (pending-amber) com seu fundo (pending-amber-tint): pendente de confirmação e o fundo das notas de aviso.

### Neutral
- **Névoa da Página** (page-mist): fundo de toda página, abaixo da faixa.
- **Branco** (surface): cartões, barra superior, modais, campos, barra inferior.
- **Branco Gelo** (surface-2): hover de linha, linhas de total e seção, bloco de dia, fundo do seletor de tipo.
- **Tinta Marinho** (ink): texto principal, valores de despesa, botão de atalho ligado, fundo do aviso (toast).
- **Tinta Média** (ink-2): rótulos de campo, texto de botão fantasma, itens de menu.
- **Cinza Ardósia** (mute): meta-texto, cabeçalhos de tabela, ícones em repouso, navegação inativa.
- **Linhas** (line, line-2, line-strong): borda de cartão e topo; divisória interna de listas e tabelas; borda de campo, botão secundário e atalhos.

### Named Rules
**The One Field Rule.** O cobalto chapado ocupa uma faixa por tela, de ponta a ponta, no topo do conteúdo. Fora dela, o azul aparece só em ações, foco e pequenos fundos claros; nunca em outro bloco grande.

**The Money Has Two Colors Rule.** Verde é só dinheiro que entra; vermelho é só alerta, atraso e negativo. Despesa é tinta, com sinal de menos. Se uma despesa comum aparece vermelha, está errado.

**The Rare Sun Rule.** O amarelo marca a sobra, a marca e a seleção. Não vira cor de botão, de texto ou de estado.

## Typography

**Display Font:** Manrope (com ui-sans-serif, system-ui, -apple-system, Segoe UI)
**Body Font:** Manrope
**Label/Mono Font:** Manrope, com números tabulares em vez de fonte mono

**Character:** Uma geométrica humanista só, em cinco pesos (400 a 800). O peso 800 com tracking negativo dá a voz de cartaz aos números da faixa; o corpo em 14px/500 mantém a leitura densa limpa.

### Hierarchy
- **Display** (800, 38px, 1.1, -0.02em): os números da faixa. Variante média de 30px quando a faixa tem números secundários. No celular, `clamp(18px, 5.6vw, 24px)`.
- **Headline** (800, 26px, 1.15, -0.02em): o título da tela dentro da faixa (22px no celular). O título do login sobe a 30px.
- **Title** (800, 16px a 17px, -0.01em): título de cartão (16px); títulos de mês nas faturas, de pessoa e de modal (17px). Totais de cartão em 22px/800.
- **Body** (500, 14px, 1.5): texto, células de tabela, campos. Títulos de linha em 600.
- **Label** (700, 13px): rótulos de campo, links de cartão, rótulos de número na faixa (600), estados.
- **Meta** (500 a 700, 12px): meta-texto das linhas, cabeçalhos de tabela (700), ajuda de campo. Rótulos da barra inferior em 11px/700.

### Named Rules
**The Tabular Everywhere Rule.** O corpo inteiro roda com `tnum` e `lnum`. Todo valor em dinheiro sai pelo formato `brl` (`1.234,56`, menos tipográfico `−` para negativo), `rs` quando leva o símbolo (`R$ 1.234,56`) ou `signed` (`+`/`−` pelo tipo), alinhado à direita e sem quebra.

**The No Small Caps Rule.** Não há texto em caixa alta, tracking positivo ou rótulo acima de título. Hierarquia vem de peso e tamanho.

## Layout

Página centrada com largura máxima de 1360px e calha de 40px (24px abaixo de 1080px, 16px abaixo de 860px). A faixa ocupa a largura toda e seu conteúdo segue a mesma coluna da página. Abaixo dela, a página empilha blocos com 20px de intervalo; o painel usa três colunas iguais (duas abaixo de 1080px, uma abaixo de 860px), e telas de detalhe usam 2:1. Os números da faixa entram numa grade automática com mínimo de 190px por número, 28px entre colunas.

Dentro de cartões o ritmo é 18–20px de borda e 10–12px por linha; linhas de lista e tabela são separadas por divisórias de 1px, não por espaço. Filtros ficam num cartão próprio em grade automática de 170px; no celular eles se recolhem atrás de um "Filtros" de 44px.

**Celular (até 860px).** A barra superior baixa para 54px e perde a navegação; uma barra inferior fixa de 62px traz Painel, Lançamentos, Faturas, Contas e Menu, e o Menu abre uma folha com todas as telas. Tabelas marcadas como responsivas viram linhas empilhadas: título no topo, valor fixo no canto superior direito, meta-texto abaixo (com o rótulo da coluna quando precisa), ações à direita no fim; nas tabelas com ações em linha as ações sobem para a coluna da direita, centradas nas linhas de meta. Botões de ícone crescem para 44x44px. Formulários passam a uma coluna e os botões do rodapé do modal dividem a largura. Avisos descem para cima da barra inferior.

**Select2** só entra com ponteiro fino (computador) em listas de 8 opções ou mais, e sempre nos campos de escolha múltipla; no celular os campos simples ficam nativos.

## Elevation & Depth

Plano por padrão. Faixa, cartões, filtros, tabelas e barra superior não têm sombra; a profundidade vem do contraste cobalto/névoa/branco e de bordas de 1px. A única sombra do sistema é a de flutuação, usada no que fica por cima do conteúdo: menus da navegação, modal, diálogo de confirmação, aviso, barra de ações em massa e lista do Select2. Um véu marinho (scrim) escurece o fundo atrás de modais e da folha de menu.

### Shadow Vocabulary
- **Flutuação** (`box-shadow: 0 12px 32px rgba(20, 33, 61, .16), 0 2px 6px rgba(20, 33, 61, .08)`; no escuro `0 12px 32px rgba(0,0,0,.45), 0 2px 6px rgba(0,0,0,.3)`): camadas que flutuam.
- **Botão do seletor** (`box-shadow: 0 1px 3px rgba(20, 33, 61, .14)`): só a opção marcada do seletor Despesa/Receita, que se destaca do trilho.

### Named Rules
**The Flat Paper Rule.** Se está no fluxo da página, não tem sombra. Sombra significa "isto está por cima e vai sumir".

## Shapes

Cantos suaves e consistentes: 10px em cartões, filtros, notas e avisos; 8px em botões, campos, atalhos, bloco de dia e botões da faixa; 12px no modal, no diálogo de confirmação e na barra de ações em massa; 16px só no topo das folhas que sobem no celular. Badges usam 6px, etiquetas 5px; a barra de proporção tem 10px de altura com pontas de 5px e as barras de categoria 6px com pontas de 3px. Bordas são sempre de 1px, exceto a linha de total final do relatório (2px). Marcas de estado são círculos de 9px; o ponto de categoria é um quadrado de 9px com canto de 3px.

A marca é feita da própria barra de proporção: um bloco cobalto de 15px e um amarelo menor, lado a lado, com 2px de vão e cantos de 2px; o favicon repete o desenho em branco e amarelo sobre um quadrado cobalto.

## Components

### A Faixa (assinatura)
Campo cobalto chapado, de ponta a ponta, sempre o primeiro bloco do conteúdo, uma por tela. Traz o título da tela (headline), uma linha de contexto em branco a 84%, ações à direita (botão branco com texto cobalto, ou o botão quieto em branco a 12%) e de dois a quatro números em display, cada um com rótulo acima e nota abaixo. Quando a tela tem parte/todo, a **barra de proporção** fica logo abaixo dos números: trilho branco a 20%, parte "usada" em branco, parte "sobra" em amarelo, e uma legenda de dois lados (esquerda e direita) com o percentual em negrito. A barra cresce da esquerda uma vez ao carregar (0,9s, `cubic-bezier(.16, 1, .3, 1)`). Navegação de mês em quadrados de 34px a 12% de branco. Alerta dentro da faixa: pílula a 14% de branco com ícone amarelo. Telas de lista herdam a faixa do layout de lista, que resume o que a tabela mostra (total filtrado, a pagar, disponível). O login usa a mesma faixa, centrada, com o cartão de entrada sobreposto à borda inferior.

### Buttons
- **Shape:** cantos de 8px, altura 36px (30px na versão pequena), texto 14px/700.
- **Primary:** cobalto com texto branco; no escuro, azul claro com texto noite.
- **Hover / Focus:** escurece para cobalto fundo; transição de cor de 0,12s. Foco é um contorno de 2px cobalto afastado 2px (branco dentro da faixa).
- **Secondary:** branco com borda forte; no hover a borda e o texto ficam azuis.
- **Ghost:** transparente, tinta média; hover em branco gelo.
- **Danger:** vermelho com texto branco, só para excluir.
- **Icon button:** 32px (44px no celular), cinza em repouso; a versão de perigo ganha fundo vermelho claro no hover.

### Chips e atalhos
- **Atalhos de filtro (segmentado):** pílulas de 30px com borda forte e canto de 8px; a ligada fica em tinta marinho com texto branco.
- **Badges:** 22px, canto de 6px, 12px/700, em quatro tons (azul, verde, vermelho, âmbar) mais o neutro.
- **Categoria:** ponto quadrado na cor da categoria, cadastrada pelo usuário, seguido do nome. A cor da categoria aparece só no ponto e na barra de categoria.

### Marcas de estado
Círculo de 9px antes do texto do estado, 13px/600: **cheio verde** = confirmado ou ativo; **vazado âmbar** = pendente; **cheio vermelho** = atrasado; **vazado cinza** = desligado. Quando a marca é um botão (confirmar com um clique), o hover sublinha o texto.

### Cards / Containers
- **Corner Style:** 10px.
- **Background:** branco sobre a névoa da página.
- **Shadow Strategy:** nenhuma (ver Elevation & Depth).
- **Border:** 1px na cor de linha; divisórias internas em line-2.
- **Internal Padding:** cabeçalho 16px 20px, corpo 10px 20px 16px, bloco cheio 18px 20px (16px laterais no celular). Cabeçalho de cartão: título à esquerda e um link azul de 13px/700 à direita. Cartão desligado cai para 72% de opacidade.

### Listas e tabelas
Cabeçalho em 12px/700 cinza, células de 11px 12px, divisória line-2, hover de linha em branco gelo, valores em `amount` (700, tabular, à direita). Linhas de total e seção ficam em branco gelo com peso 800. **Linha apagada** (ignorada, desfeita): texto cinza e valor riscado. **Linha atrasada**: data e valor em vermelho. O **bloco de dia** (44px, dia em 17px/800 e mês abreviado embaixo) marca o que vence: vermelho claro se venceu, névoa cobalto se é hoje. Linhas filhas (caixinhas, cartões adicionais) levam um pequeno L de 2px antes do nome. Paginação no rodapé do cartão, 20 por página.

### Estados vazios
Centrados, 44px de respiro vertical: uma frase em tinta 15px/700 dizendo o que falta e uma frase cinza dizendo o que fazer ou o que vai aparecer, com o botão primário quando há uma ação direta.

### Inputs / Fields
- **Style:** 38px, borda forte de 1px, canto de 8px, fundo branco, 14px/500 tabular. Seletores nativos com a seta desenhada à direita.
- **Focus:** borda cobalto e anel de 3px a 18% do cobalto; hover escurece a borda.
- **Error / Disabled:** borda vermelha, mensagem de 12px/600 vermelha abaixo; erros gerais numa caixa vermelho claro. Rótulos em 13px/700 com "(opcional)" em cinza 500.
- **Seletor Despesa/Receita:** trilho branco gelo de canto 10px com duas opções; a marcada vira branca com a sombra de botão e, se for receita, texto verde.
- **Linha de opção:** caixa com borda, checkbox de 18px em cobalto, título e explicação de 12px.

### Navigation
Barra superior branca de 58px, fixa, borda inferior de 1px: marca à esquerda, grupos de navegação em 14px/600 cinza que abrem menus flutuantes (itens com ícone, título e sublinha de 12px), botão "Nova transação" à direita, tema e conta em botões de ícone. O ativo fica em tinta com um sublinhado cobalto de 3px na base da barra; no menu, o item ativo ganha névoa cobalto. No celular: barra inferior de cinco itens (ícone de 22px sobre rótulo de 11px/700, ativo em azul) e folha de menu com alça, canto de 16px no topo, subindo em 0,22s.

### Modal e folha
Painel branco de canto 12px, 640px (440px pequeno, 820px grande), cabeçalho e rodapé fixos separados por divisórias, corpo que rola. Entra subindo 10px com leve escala (0,2s) sobre o véu marinho. No celular vira folha de largura total colada embaixo, canto de 16px no topo, até 94% da altura, com o rodapé respeitando a área segura. Confirmações usam um diálogo nativo de 420px no mesmo estilo.

### Avisos
Toast em tinta marinho com texto branco e ícone verde claro (vermelho com texto branco para erro), canto de 10px e sombra de flutuação; no alto à direita no computador, acima da barra inferior no celular.

## Do's and Don'ts

### Do:
- **Do** abrir toda tela nova com uma faixa cobalto, uma só, com 2 a 4 números dessa tela e a barra de proporção quando houver parte/todo.
- **Do** formatar todo valor com `brl`, `rs` ou `signed`, em números tabulares, alinhados à direita.
- **Do** usar verde só para receita e confirmado, vermelho só para atraso, erro e negativo, e deixar despesa em tinta com sinal de menos.
- **Do** dar a cada tabela nova o comportamento de linhas empilhadas no celular, com o valor no canto superior direito e alvos de toque de 44px.
- **Do** escrever estados vazios com o que falta e o que fazer, em português direto.
- **Do** manter o par claro e escuro completo em cada token novo.

### Don't:
- **Don't** colocar um segundo campo de cobalto chapado, cards de KPI coloridos ou gráficos decorativos na tela.
- **Don't** pintar despesas comuns de vermelho nem usar o amarelo como cor de botão, texto ou estado.
- **Don't** dar sombra a cartões, tabelas ou à faixa; sombra é só para o que flutua.
- **Don't** usar texto em caixa alta, tracking positivo ou rótulo pequeno acima de títulos.
- **Don't** criar animação nova além da barra de proporção, da subida do modal e da folha; o resto são transições de cor e o giro das setas de menu.
- **Don't** carregar Select2 em campos simples no celular.
