# Guia de uso

Como usar o assistente no Telegram e o site no dia a dia. A parte técnica (instalação, variáveis, deploy) está no [README](../README.md).

## A ideia em uma frase

Você manda ao bot o que tiver (fatura, extrato, comprovante, uma frase), ele monta um **lote** com os lançamentos e você confirma com um toque. Nada é gravado sem a confirmação, e todo lote confirmado pode ser desfeito com `/desfazer`.

## Primeiro uso, na ordem que dá menos trabalho

1. **Confira os cadastros no site.** Contas, cartões e categorias que já existem serão reaproveitados. Em cada cartão de crédito, preencha o dia de fechamento e o de vencimento (se faltar, o bot preenche na primeira fatura que você confirmar).
2. **Apresentem-se ao bot.** Cada pessoa, do seu próprio Telegram:
   - "Sou o Fulano. Nos documentos apareço como FULANO DE TAL."
   - "Cadastre minha esposa Maria, que aparece como MARIA DE TAL."
   - Ela, do Telegram dela: "Sou a Maria."

   O chat de cada pessoa precisa estar liberado no servidor (`TELEGRAM_ALLOWED_CHAT_IDS`). Para descobrir o número do chat, a pessoa manda qualquer mensagem ao bot (ele não responde enquanto o chat não está liberado) e o número aparece no admin do site, em "Telegram updates", na coluna `chat_id`.
3. **Diga de quem é cada conta.** "O Inter e o Nubank são da Maria; o resto é meu." Caixinhas herdam o dono da conta, e cartões herdam o da conta.
4. **Informe os saldos de hoje.** "Meu saldo no Mercado Pago hoje é 1.250,00; na caixinha Emergências tenho 8.000 e na caixinha Viagem 2.300." É o ponto de partida de todas as projeções. O extrato da conta não mostra o saldo das caixinhas, por isso elas precisam ser ditas.
5. **Ensine o que se repete.** Veja "Regras permanentes" abaixo. Vale responder já as perguntas que o bot costuma fazer.
6. **Envie os documentos, um mês de cada vez, do mais antigo para o mais novo.** Comece pelos extratos das contas e depois as faturas do mesmo mês. Se enviar extratos de várias contas do mesmo período, as transferências entre elas se encaixam sozinhas.
7. **Confirme cada lote antes de enviar o próximo documento do mesmo cartão ou conta.** O bot só reconhece como "já registrado" o que foi confirmado.

## O que mandar

| O que | Como | Resposta |
|---|---|---|
| Fatura de cartão, extrato (PDF, CSV, OFX) | Anexe o arquivo | Em alguns minutos (leitura em segundo plano, mais barata) |
| O mesmo, com pressa | Anexe com a legenda `agora` | Na hora, pelo dobro do preço |
| Comprovante (Pix, cartão, boleto) | Foto ou print | Na hora |
| Gasto do dia | "almoço 45 no pix", "TV 2400 em 12x no Nubank" | Na hora |
| Saldo | "meu saldo no Inter hoje é 3.200" | Na hora |
| Pergunta | "quanto vou pagar de fatura em dezembro?" | Na hora |

PDF com senha: o bot pede a senha e apaga a sua mensagem em seguida. Senhas que se repetem (os primeiros dígitos do CPF, por exemplo) podem ficar no servidor em `PDF_PASSWORDS`, e aí ele abre sozinho.

Uma legenda no arquivo ajuda: "fatura do cartão da Maria", "extrato da conta PJ".

## O lote

O resumo mostra quantos itens serão gravados, quantos já estavam registrados, e as conferências:

- **Fatura:** a soma dos itens precisa bater com o total da fatura, e o subtotal de cada cartão com o "Total para..." impresso.
- **Extrato:** saldo inicial mais as linhas precisa dar o saldo final.

Se aparecer "diferença de R$ ...", não confirme: peça "confira de novo, falta alguma linha" ou reenvie com a legenda `agora`.

Botões: **Confirmar**, **Ver itens** (lista numerada) e **Descartar**. Para ajustar, escreva no chat usando o número do item:

- "o item 3 é mercado"
- "tira o 5"
- "o item 8 foi no cartão da Maria"
- "inclui o item 4" (um item que ele achou que já existia)
- "os itens 12 e 40 são do João" (cartão emprestado, veja abaixo)

Depois de um ajuste chega um resumo novo. Use sempre os botões do resumo mais recente; os antigos deixam de valer.

`/desfazer` desfaz o último lote confirmado, inclusive cartões e caixinhas que ele tenha criado.

## Cartões

- **Fatura com vários cartões** (titular, adicional, virtual): é uma fatura só, mas cada compra fica no cartão que a fez. Os cartões adicionais ficam ligados ao principal pelo campo "Cobrado na fatura de". Você não precisa configurar isso à mão: quando a fatura traz um cartão novo, o bot propõe o cadastro já ligado; quando traz um cartão que você já cadastrou solto, o resumo avisa "Ao confirmar, ligo à fatura de X: ..." e a ligação é feita no Confirmar (o `/desfazer` desfaz).
- **Parcelas:** a linha "PARCELA 03/10" vira uma compra parcelada com as dez parcelas; nas faturas seguintes cada parcela já aparece como registrada.
- **Pagamento da fatura:** não é gasto. No extrato da conta, vira uma transferência para o cartão e marca aquela fatura como paga.

## Caixinhas e cofrinhos

São subcontas dentro de uma conta. Guardar e retirar dinheiro é transferência, não gasto nem receita. O "disponível" mostra só as contas; o "guardado" aparece à parte e não entra na projeção de saldo (mas o bot lembra dele quando um mês fica negativo).

## Cartão emprestado (compras de outras pessoas)

Quando alguém de fora da família compra no seu cartão e devolve depois:

- **Marque a compra:** depois de receber o lote da fatura, diga "os itens 12 e 40 são do João". A compra continua na fatura (o banco cobra de você), mas sai dos gastos da família e entra na conta do João. Funciona também para itens que já estavam registrados.
- **Parcelas:** marcou uma vez, as parcelas seguintes já vêm como dele nas próximas faturas.
- **Compra antiga, já confirmada:** "a compra da Loja X de outubro foi do João".
- **Cartão que fica com a pessoa:** "o cartão final 1234 fica com a Ana". Tudo que vier nele passa a ser dela por padrão; se uma compra foi sua, diga "o item 7 é meu".
- **Devolução:** "o João me pagou 300 no Pix do Nubank", ou simplesmente importe o extrato: um Pix recebido de quem está devendo é reconhecido como devolução. Não conta como receita.
- **Quanto cada um deve:** `/terceiros`, ou pergunte "quanto o João me deve?". "Monte a cobrança do João" devolve um texto com os itens e o total, pronto para encaminhar.
- O aviso de fatura vencendo diz quanto daquela fatura é de cada pessoa.

A projeção de saldo considera a fatura inteira saindo da conta. O que os outros vão devolver aparece à parte e não é contado como certo.

Ainda não dá para dividir um item (metade sua, metade de outra pessoa). Por enquanto, peça ao bot para trocar o item por dois lançamentos.

## Regras permanentes

O que você responder uma vez pode valer para sempre. Diga "lembre que..." ou apenas responda a dúvida; o bot guarda a regra e avisa que guardou. Exemplos:

- "Lembre que Pix para a minha empresa é gasto, categoria Serviços."
- "Pagamento de fatura no extrato do Mercado Pago é sempre do cartão Mercado Pago."
- "Compras no Posto Y são sempre Combustível."

Para ver ou mudar: "quais regras você tem guardadas?", "esqueça a regra do posto".

Pix para você mesmo em outro banco: o bot lança só a saída da conta do extrato. Quando o extrato da outra conta for importado, os dois lados se juntam numa transferência só. Se a outra conta nunca for importada, o dinheiro fica como "saiu para uma conta sua"; nesse caso, informe o saldo dela de vez em quando.

## Perguntas que funcionam bem

- "Quanto gastei com mercado este mês? E no mês passado?"
- "Quanto vou pagar de fatura em dezembro, por cartão?"
- "Qual meu saldo hoje? E o previsto para o fim de janeiro?"
- "Vai sobrar dinheiro este mês?"
- "Quanto cada um de nós gastou em outubro?"
- "Quanto está com cada um?"
- "Quais parcelas terminam nos próximos três meses?"
- "Quanto o João me deve?"

Diga o período quando ele importar. O bot responde com os números do sistema e informa o período que considerou.

## Avisos automáticos (8h)

- Fatura vencendo em até três dias e no dia do vencimento.
- Saldo projetado negativo neste mês ou no próximo (no máximo um por semana).
- Resumo do mês anterior, nos primeiros dias do mês, com o que há a receber de terceiros.

Só aparecem quando há dados: cartões com dia de vencimento e contas com saldo informado.

## Comandos

| Comando | O que faz |
|---|---|
| `/novo` | Começa uma conversa nova (o bot esquece o assunto anterior, não os dados) |
| `/desfazer` | Desfaz o último lote confirmado |
| `/terceiros` | Quem deve quanto no cartão emprestado |
| `/custo` | Gasto com IA no mês |
| `/cancelar` | Cancela o pedido de senha de PDF |
| `/ajuda` | Resumo do que o bot faz |

## Custos

Medido em documentos reais (novembro de 2026):

| Operação | Custo aproximado |
|---|---|
| Fatura de 199 linhas, em segundo plano | US$ 0,17 |
| A mesma fatura com a legenda `agora` | US$ 0,34 |
| Extrato mensal de uma conta, em segundo plano | US$ 0,07 |
| Pergunta ou lançamento por texto | alguns centavos |

`/custo` mostra o gasto do mês. O servidor tem um orçamento mensal (`AI_MONTHLY_BUDGET_USD`, avisa por e-mail aos 80% e aos 100%) e um teto (`AI_MONTHLY_LIMIT_USD`): ao chegar no teto, o bot para de usar IA até o mês virar, e os comandos, os botões e os avisos continuam funcionando.

Para gastar menos: prefira o envio normal ao `agora`, mande o arquivo original em vez de foto de tela, use `/novo` ao mudar de assunto (conversas longas custam mais a cada mensagem) e junte os gastos do dia numa mensagem só.

## Dicas e limites

- **OFX é melhor que PDF** para extratos, quando o banco oferece: cada linha traz um identificador, e reimportar nunca duplica.
- **Não reenvie por garantia.** Reenviar uma fatura já confirmada não duplica nada (tudo aparece como "já registrado"), mas custa uma leitura.
- **Documento de outro mês ou de outra pessoa:** diga na legenda. O bot identifica a conta pelo banco e pelo titular impressos; se você tem duas contas no mesmo banco, a legenda evita a pergunta.
- **Dia de fechamento:** o dia cadastrado no cartão é só uma estimativa, porque o banco desloca o fechamento (fins de semana, feriados). Cada fatura que você confirma guarda a data real de fechamento e vencimento daquele mês, e a partir daí as compras, inclusive as que você lançou antes sem fatura, são encaixadas na fatura certa pela janela real. Para os meses ainda sem fatura importada, vale a estimativa.
- **O site e o bot mostram os mesmos números.** Correções pontuais (categoria, valor, data) podem ser feitas no site.
- **Fotos:** uma por comprovante, legível e sem cortes. Fotos enviadas juntas são lidas na mesma resposta.
- **O bot não lê:** áudio, vídeo e links.
- **Privacidade:** os arquivos ficam no seu servidor. Para a leitura, o conteúdo é enviado à API do provedor de IA configurado.

## Para quem administra

- **Backup:** todo dia às 3h30, em `/var/backups/confin` no servidor (banco e arquivos recebidos). Ficam os últimos 14 dias e o do dia 1 de cada mês por um ano. Se falhar, chega um e-mail. Os backups estão no mesmo servidor: copie-os para outro lugar de tempos em tempos.
- **Restaurar:** `pg_restore --clean --if-exists --no-owner -d confin /var/backups/confin/db-<data>.dump` para o banco e `tar -xzf /var/backups/confin/files-<data>.tar.gz -C <pasta acima da pasta de arquivos do bot>` para os arquivos.
- **E-mails de aviso** vão para `ALERT_EMAIL`. Teste: `python manage.py send_alert "teste"`.
- **Logs:** `journalctl -u confin -u confin-worker -f`.
- **Liberar outra pessoa no bot:** acrescente o número do chat dela em `TELEGRAM_ALLOWED_CHAT_IDS` (separado por vírgula) e reinicie `confin` e `confin-worker`.
