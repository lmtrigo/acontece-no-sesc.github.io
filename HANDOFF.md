# Handoff — Agenda Sesc SP

Documento de contexto para retomar o projeto em outra conversa. Contém as
decisões, as descobertas sobre a fonte de dados e as armadilhas já resolvidas,
para não serem reintroduzidas.

**Pasta do projeto:** `C:\Users\leand\SESC`
**Prévia publicada:** https://claude.ai/code/artifact/10190c1d-a88a-4f8e-a237-2bdb49e16ef6
**Estado:** 9 commits locais, repositório pronto para `git push`. Falta só publicar.

---

## 1. O que é

Agregador **não oficial** da programação do Sesc São Paulo (capital, interior e
litoral). App de celular instalável como PWA, com destaques, agenda, favoritos
e acompanhamento de sorteios.

Números atuais: **2.119 eventos** retidos de 2.477 coletados, janela de
11/08/2026 a 09/10/2026.

Regra ética adotada desde o começo: nunca imitar a identidade visual do Sesc,
sempre linkar de volta para a página oficial, e deixar visível que não é site
oficial. O app não pede login do Sesc e não coleta nada de quem usa.

---

## 2. As fontes de dados (o achado principal)

Nenhuma exigia chave. Foram descobertas inspecionando o tráfego do portal.

### 2.1 Listagem — API REST do WordPress

```
GET https://www.sescsp.org.br/wp-json/wp/v1/atividades/filter
    ?data_inicial=2026-08-15&data_final=2026-08-15
    &tipo=atividade&dinamico=true&ppp=300&page=1
```

Envelope: `{editorial, atividade[], total:{value}}`. A lista contém `null` no
meio — é preciso filtrar.

Campos úteis: `id`, `id_java`, `titulo`, `complemento`, `link`, `unidade[]`,
`tipos_linguagens[]` (categoria + subcategoria), `publico_tag[]`, `conjunto[]`
(projeto), `gratuito`, `esgotado`, `qtdeIngressosWeb`, `dataPrimeiraSessao`,
`dataUltimaSessao`, `quantDatas`.

**E `imagem` + `imagens{}`** — a foto da atividade. `imagem` é a original (chega
a 3 MB); `imagens` traz as variantes **só com o nome do arquivo**, na mesma
pasta. O coletor monta três URLs a partir daí (`thumb`, `img`, `capa`), uma
para cada uso na tela. Ficou um ano fora do coletor por não ter sido notada.

**Armadilha da paginação:** a listagem vem com `null` no meio, então uma
página cheia devolve **299** e não 300. Parar em "menos que `ppp`" cortava a
varredura na primeira página — o fim é a página **vazia**. Foi isso que fez a
primeira passada de fotos achar 1.569 de 2.342; corrigido, achou 3.582 itens e
só 14 eventos futuros ficaram sem foto.

**Armadilha conhecida:** o filtro de data **omite eventos**. "Ecos da
Independência" (12/09) não volta na consulta de 12/09, mas aparece na listagem
sem filtro. Por isso `coletor.py` faz uma varredura geral depois do dia a dia —
recuperou 53 eventos, 25 deles Turismo Social.

### 2.2 Regiões das unidades

```
GET https://www.sescsp.org.br/wp-json/wp/v1/unidades-atividades
```

O campo `description` já traz `capital` | `interior` | `litoral`. São 43
unidades: 25 capital, 16 interior, 2 litoral. **Endereço não vem aqui.**

O endereço está no HTML da página da unidade, em `data-geo-address` (e o link
do mapa em `data-como-chegar`), em `/unidades/<group_slug>/`. `extras.py`
raspa as 43 e grava em `unidades[].endereco`. Antes o endereço vinha só da
bilheteria, que cobre 32 unidades — as 9 que não vendem ingresso (Interlagos,
Itaquera, Osasco, Bertioga…) ficavam sem, e o `.ics` saía sem local.

### 2.3 Bilheteria — preços, sessões exatas e datas de venda

Indexada pelo `id_java` que vem na listagem:

```
GET https://portal.sescsp.org.br/bilheteria/atividade.action?idAtividade=253940
```

Entrega por sessão: `valorComerciario` / `valorMeia` / `valorInteira`,
`dataInicialSessaoFmt` (data e hora **exatas**), `dataInicialVendaOnlineFmt`,
`dataInicialVendaRedeFmt`, `statusSessaoSesc`, `qtdeIngressosWeb/Rede`,
`urlCompra`, `maxTicketSessao`. E no evento: `classificacaoMinina`,
`unidadePrincipal` com endereço e lat/lng.

Confirma a regra das 24h: venda on-line abre exatamente 24h antes da presencial.

**Só cobre quem tem `id_java`.** Turismo Social **não tem** — passeios não são
vendidos como ingresso. Para eles o preço vem do HTML (ver 2.4). Foi por isso
que 95 passeios ficaram sem preço numa versão.

### 2.4 Página do evento — descrição, inscrição, sorteio, preço do turismo

Não há endpoint de detalhe (conferido em `/wp-json/wp/v1`). Extração do HTML,
apoiada em classes estáveis:

- `.evento--sessao--entrada--preco` → pares `<span class="valor">` + `.label`
- `.info_local` → "Inscrições: 7/8 às 14h a 12/8 · Sorteio: 13/8 às 15h"
- Corpo da página → "Cronograma:" ou "INSCRIÇÕES" (Turismo Social)
- Lista de contemplados → o cabeçalho **não é um só**. `Resultado do Sorteio:`
  cobria o Turismo Social clássico; "Minas em Cena" publica sob um
  `CONTEMPLADOS` seco, logo depois de "Compartilhe:". Enquanto o extrator
  conhecia só a primeira forma, o app afirmava que a lista não tinha saído com
  ela na tela. Hoje reconhece quatro formas, percorre **todas** as ocorrências
  e fica com a maior lista — "sorteados" e "contemplados" também aparecem em
  prosa ("os sorteados poderão efetivar o pagamento"), e a trava é exigir um
  código nos dois primeiros tokens depois do cabeçalho, o que em prosa nunca
  acontece.
- Descrição → texto entre "Compartilhe:" e o primeiro bloco de serviço
- Cabeçalho → **"Duração: 50 minutos"**. Está na página e não na API; é o
  segundo degrau da regra de término do `.ics`. Ficou de fora por muito tempo
  porque foi procurada nas *descrições já coletadas*, que vêm truncadas — e lá
  ela não aparece nunca.
- Corpo → **regras recorrentes de inscrição** (`inscricao.regras`), ver 4.7

---

## 3. Armadilhas de extração já resolvidas

Cada uma custou uma rodada de depuração. **Não reintroduzir.**

| Problema | Correção |
|---|---|
| `<script>` tinha as tags removidas mas o **código ficava** na descrição | `RE_INVISIVEL` remove o conteúdo de script/style/svg antes de limpar |
| "Inscri**ção**" no singular nunca casava — o padrão exigia `[õo]` e a palavra tem **ã** | `Inscri[çc](?:[ãa]o\|[õo]es)`. Corrigiu 78 eventos |
| "Inscrições **de 6 a 10/8**" lia o **fim** como início (match ancorado falhava no "de ") | Prefixo opcional descartado + busca não ancorada |
| Janela de 90 caracteres perdia datas distantes do rótulo | Janela de 260, cortada no próximo rótulo (`RE_PROX_ROTULO`) |
| "Inscrição para **o sorteio**:" fazia o período de inscrição virar data do sorteio | Lookbehind `(?<!para )(?<!para o )` |
| Correção de ano comparava com o **início** do evento — temporada longa jogava a inscrição para o ano anterior | Compara com o **fim**, e só com folga > 60 dias |
| Rótulo "INSCRIÇÕES" era engolido pelo próprio regex, texto começava em ":" | Captura inclui o rótulo |
| "Divulgação dos sorteados" / "Sorteio e divulgação ... em 25/06" não reconhecidos | Padrões adicionais sem dois-pontos |

---

## 4. Regras de negócio

### 4.1 Retenção (`regras.py`)

O corte é pela **data de entrada**, não pela data do evento — a inscrição de um
passeio de novembro abre em agosto. Fica no app quem satisfaz uma destas:

1. inscrição ou venda **abre** nos próximos 60 dias;
2. inscrição ou venda **está aberta** agora;
3. acontece em 60 dias e **nada indica** que a entrada fechou.

Mais: **Turismo Social sem data de inscrição sai** (ou já passou da fase, ou não
dá para saber como entrar).

**Esgotado e prazo vencido não excluem mais.** Os dois eram tratados como
"barreira fechada" e tiravam o evento da base inteira — 41 esgotados e 306
inscrições encerradas que *acontecem* nas próximas semanas sumiam da agenda
sem nenhuma explicação na tela. São estado da entrada, não fim da atividade.
Agora ficam, com as etiquetas **"Esgotado"** e **"Inscrição encerrada"**; quem
decide se vale a pena é quem lê, não o corte. Isso trouxe a base de 1.324 para
1.644 eventos, 242 deles cursos e oficinas.

O coletor descarta apenas os **cancelados**. A categoria **"Outros"** — o balde
do que o portal não classificou — passou a ser mantida: jogá-la fora tirava da
agenda atividades reais, cujo único defeito era não ter rótulo. No app ela
aparece como qualquer outra categoria, com a cor neutra de reserva.

Ponto delicado: "barreira fechada" só conta com **data**. Centenas de eventos
têm bloco de inscrição em prosa sem data ("inscrições no local", "lista de
espera"); tratá-los como fechados descartava 62% do catálogo.

### 4.2 Estados de inscrição (no app)

- `futura` — abre depois de hoje
- `aberta` — prazo explícito ainda válido, **ou** presumido (abertura + 3 dias)
- `encerrada` — prazo passou

Sem prazo publicado, o app assume **abertura + 3 dias** e mostra "(estimado)"
com aviso para confirmar no site. Nunca afirmar "aberta" sem base.

### 4.3 Viagens de vários dias

Turismo Social é **contínuo**: viagem de 11 a 16/08 acontece nos seis dias.
`expandir_viagens` preenche o intervalo e marca `continuo: true`.

Só vale para Turismo Social. Exposição também tem início e fim distantes mas
fecha às segundas — ali os dias coletados é que estão certos.

**O campo `temporada` da API não serve como critério**: vem `False` para
exposições com dias fixos e `True` para passeios.

### 4.4 Relevância dos destaques

Procura 40% (ingressos restantes), custo 35% (gratuidade), raridade 25%
(sessão única vale mais que temporada). **Não existe nota da crítica no portal**
— não inventar. Esgotados saem dos destaques: recomendar o que não dá para
assistir é frustração.

---

### 4.5 O que é novidade

"Entrou agora na programação" não se descobre olhando só a base de hoje. Quem
compara é o **coletor**: antes de gravar, ele lê a coleta anterior e carimba
cada evento com `visto` — a data em que apareceu pela primeira vez. Quem já
estava lá conserva o carimbo antigo; quem não estava recebe a data de hoje.

- A primeira coleta com rastreio **não carimba ninguém**: ela estabelece a
  linha de base e grava `rastreioDesde` no arquivo. É esse campo que separa
  "base anterior ao rastreio" de "base sem novidades", e é o que faz o dia 2
  já valer.
- Sem essa trava o primeiro dia mentiria duas vezes. Medido no ensaio de
  18/08 contra a base de 13/08: **607 eventos** seriam marcados como novos,
  e **359 deles eram os "Outros"** — atividades que sempre estiveram no
  portal e que só entraram porque *nós* mudamos a regra. O trilho abriria com
  59% de entulho retroativo.
- Quem já estava na base e não tem carimbo fica **sem** carimbo: é anterior
  ao rastreio e não dá para inventar uma data. Herdar a data da coleta
  anterior também seria armadilha — a base de 13/08 estava a seis dias da
  primeira rodada, dentro da janela de sete.
- Ressalvas: um evento que suma da listagem por um dia e volte é carimbado de
  novo, e a janela que anda um dia por vez carimba a borda — medido, 3 eventos
  em 5 dias. É o preço de não guardar um histórico de ids que cresceria para
  sempre.

O app mostra o que tem `visto` nos últimos **7 dias** (`DIAS_NOVIDADE`), no
trilho "Novidades na programação" e no chip "Novidades" da agenda.

### 4.7 Inscrição sem data, com regra

Parte das inscrições não publica data nenhuma: publica uma **regra**, em
prosa, que se repete todo mês. O caso que motivou o suporte, num curso de
natação do Bom Retiro:

> As vagas disponíveis são liberadas prioritariamente para pessoas portadoras
> de **Credencial Plena na 1ª e na 3ª quinta-feira** de cada mês a partir das
> **18h**. Caso estas vagas não sejam preenchidas, serão disponibilizadas para
> o **público em geral na 2ª e na 4ª quarta-feira** a partir das **14h**.

São **duas datas diferentes para duas pessoas diferentes**, e nenhuma das duas
existe como data em lugar nenhum da fonte. `detalhes.py` extrai isso em
`inscricao.regras`:

```json
[{"quem": "plena", "semanas": [1, 3], "dow": 4, "hora": "18:00"},
 {"quem": "geral", "semanas": [2, 4], "dow": 3, "hora": "14:00"}]
```

`dow` segue a convenção do JavaScript (0 = domingo) porque quem consome é o
app. O extrator ancora no trecho "<dia da semana> de/do/no mês", lê os ordinais nos
110 caracteres anteriores e a hora nos 90 seguintes.

**O público vem antes ou depois da regra**, e ler só para trás não basta:

- antes — "para portadores de Credencial Plena **na 1ª e na 3ª quinta-feira**…"
- depois — "As vagas são liberadas na 1ª e 3ª quinta-feira de cada mês, a
  partir das 18h, **para quem possui credencial plena**"

A segunda forma virava `todos`, e com isso quem **não** tem Credencial Plena
via uma data que não era dele. Agora olha nos dois sentidos.

**Os ordinais ficam em algarismo de propósito.** Por extenso, "segunda",
"quarta" e "quinta" são também dias da semana: ler "primeira e segunda
quinta-feira" como ordinal daria uma data errada, que é pior do que não dar
data nenhuma.

O app calcula a próxima ocorrência de cada janela e **pergunta uma vez** se a
pessoa tem Credencial Plena, guardando a resposta em `agenda.credencial`. Sem
a resposta ele mostra as duas e marca a que abre primeiro, com o aviso de que
falta escolher — mostrar a quinta-feira da Credencial Plena para quem só entra
na quarta seguinte seria pior do que não mostrar nada.

O `.ics` do lembrete usa a data que é **daquela pessoa**. Por isso ele nunca
vem de arquivo servido: `publicar.py` só gera `-insc.ics` para data publicada,
já que não dá para servir uma versão por credencial.

### 4.6 Fuso horário

Tudo o que é "hoje" e "agora" é **horário de Brasília**, fixo em UTC−3 (o Brasil
não usa mais horário de verão desde 2019).

O robô roda em UTC no GitHub Actions: `geradoEm` saía sem fuso e o app exibia a
coleta três horas adiantada, além de arriscar carimbar o dia seguinte numa
execução de madrugada. Agora `coletor.agora_br()` grava com o deslocamento
explícito (`2026-08-18T05:10:00-03:00`) e o app converte para Brasília antes de
mostrar — inclusive carimbos antigos, sem fuso, que são lidos como já sendo
hora local da coleta.

No app, `HOJE` e `AGORA` também vêm de `agoraBR()`: com o relógio do aparelho,
quem estivesse fora do fuso via a agenda virar o dia na hora errada.

## 5. Arquitetura

```
coletor.py   → dados/eventos.json          (listagem, dia a dia + varredura)
detalhes.py  → enriquece o mesmo arquivo   (bilheteria + HTML)
extras.py    → acrescenta foto e endereço  (backfill; o coletor já grava)
reparse.py   → reprocessa sem rede         (usa o texto já guardado)
embutir.py   → prototipo.html              (arquivo único, prévia por link)
publicar.py  → web/                        (site hospedável, PWA)
```

`extras.py` existe porque `coletor.py` reescreve o arquivo do zero e
`detalhes.py` leva 70 minutos para reenriquecer: quando um campo novo aparece,
ele é acrescentado ao que já está no disco. `--fotos` pula a raspagem das
unidades. Numa coleta nova ele é dispensável para as fotos (o coletor já as
grava) mas continua sendo quem traz os endereços.

`reparse.py` é importante: `detalhes.py` guarda o texto bruto em
`inscricao.texto`, então melhorias no extrator se aplicam em segundos, sem
rebaixar milhares de páginas.

### 5.1 Duas saídas, um código

`prototipo.html` carrega com um instantâneo embutido e, se achar
`dados/eventos.json` ao lado, substitui pelo mais novo. Mesmo arquivo serve à
prévia por link (sem servidor) e ao site hospedado.

### 5.2 Descrições sob demanda

Ficam fora do pacote principal, em `dados/desc/<id>.json`, buscadas ao abrir o
evento e descartadas ao fechar. Na prévia por link não há servidor — por isso
ela é gerada com `embutir.py --com-descricao`.

### 5.2.1 O que o navegador consegue buscar do portal (e o que não)

Testado, e vale registrar porque define o que é possível em tempo real:

| endereço | CORS | serve para |
|---|---|---|
| `www.sescsp.org.br/wp-json/wp/v1/atividades/filter` | **liberado** | disponibilidade de ingressos ao vivo |
| `portal.sescsp.org.br/bilheteria/...` | bloqueado | — |
| `www.sescsp.org.br/programacao/<evento>` (HTML) | bloqueado | — |

Consequências diretas:

- **Disponibilidade** é conferida a cada abertura, direto do navegador, pela
  API de listagem: ela traz `qtdeIngressosWeb` e `esgotado`, que são os campos
  que o app mostra. Não é a base inteira — 1.644 eventos seriam doze páginas
  de 300 por abertura, e o portal não é nosso. Confere **hoje, amanhã e as
  próximas datas dos favoritos**, no máximo seis dias, e falha em silêncio.
- **Resultado de sorteio não dá para consultar na hora.** Os códigos dos
  contemplados estão no HTML da página da atividade, que é justamente o que o
  portal bloqueia. A automação possível é a que está no ar: o robô lê a lista
  todo dia e grava em `sorteados`; o app confere a cada abertura, dentro do
  aparelho. A defasagem máxima é de um dia.

### 5.2.2 O cache do service worker é o resumo da casca

Era o carimbo da **coleta** (`geradoEm`). Como o robô só coleta uma vez por
dia, qualquer mudança no app entre duas coletas não trocava o nome do cache: o
worker seguia servindo o `index.html` antigo e quem já tinha instalado nunca
via a mudança. O sintoma era sempre o mesmo — "mexi no CSS e a tela não
mudou". Agora é o **sha1 do `index.html` publicado**: mudou o app, muda o
cache.

### 5.3 Calendário

**Um `blob:` nunca abre o app de calendário** — não tem endereço que o sistema
reconheça, então o navegador sempre trata como download. O que funciona é um
`.ics` servido por **URL real** com `Content-Type: text/calendar`. O service
worker reescreve o Content-Type: nem todo host declara esse tipo (o
`http.server` do Python manda `application/octet-stream`) e sem isso o celular
não entrega ao app de agenda.

O `.ics` é montado nos dois lugares — no aparelho (`prototipo.html`) e no
servidor (`publicar.py`) — e as **duas implementações têm de dizer a mesma
coisa**. As regras, uma a uma:

| campo | regra |
|---|---|
| início | a sessão que a pessoa abriu; sem dia aberto, a próxima |
| **fim** | término publicado pela bilheteria > início + duração > **início + 30 min** |
| endereço | sempre o da **unidade** (`unidades[].endereco`), nunca só o nome |
| alertas | **1 hora, 30 minutos e 5 minutos** antes |
| fuso | gravado em **UTC** a partir de Brasília (−03:00) |

Sobre o fim: `dataFinalSessaoFmt` quase sempre **repete a hora de início** —
não é término publicado, é campo vazio disfarçado. `detalhes.py` só guarda
`sessoes[].fim` quando o valor é maior que o início. Duração não existe em
lugar nenhum da fonte (procurada nas 2,3 mil descrições: zero ocorrências), o
que faz do bloco de 30 minutos o caso comum. É deliberado: um bloco curto e
honesto ocupa menos a tarde de alguém do que duas horas inventadas.

Sobre o fuso: hora flutuante (sem `Z`) é lida no fuso do **aparelho**. Quem
abrisse a agenda fora do Brasil marcava na hora errada. Agora sai `Z`.

**Um compromisso por vez.** A versão anterior despejava todas as sessões num
arquivo só: uma temporada de dois meses entrava na agenda como sessenta
compromissos para apagar um a um. Hoje é sempre um. Viagem contínua é a
exceção — vira um único compromisso de dias inteiros (`DTEND` exclusivo), com
alerta de véspera em vez dos três, porque "em 5 minutos" não quer dizer nada
num evento de dia inteiro.

`publicar.py` gera: `<id>.ics` com a **próxima** sessão, `<id>-AAAAMMDD.ics`
por sessão para quem tem até 8 datas, e `<id>-insc.ics` da abertura. O app só
usa o arquivo servido quando ele é do **mesmo instante** que o botão está
agendando; fora disso monta no aparelho. Um `HEAD` confere antes — num deploy
incompleto o arquivo falta e o link ficaria morto.

**Sem tela intermediária.** A escolha de calendário (app / Google / Outlook /
baixar) virava uma folha inteira entre o toque e o resultado. O botão agora
faz o que diz. No computador sobra um botão **ao lado** — não no lugar — para
o Google Agenda, porque lá o `.ics` cai na pasta de downloads e parece que
nada aconteceu.

## 6. Estado atual e pendências

### Feito
Tudo o que foi pedido até aqui está implementado e verificado no navegador.

### Pendência única
**Publicar no GitHub.** O repositório está commitado (9 commits, 12 arquivos,
7,5 MB). Faltam os passos que exigem credencial do usuário:

```bash
git remote add origin https://github.com/SEU-USUARIO/agenda-sesc.git
git push -u origin main
```

Depois: **Settings → Pages → Source: GitHub Actions**, e
**Actions → Atualizar programação → Run workflow**.

O endereço sai como `https://SEU-USUARIO.github.io/agenda-sesc/`.

O robô roda todo dia às 5h10 (08:10 UTC) e leva 30 a 45 minutos.

`gh` CLI não está instalado e a conexão do GitHub não está autorizada na
sessão — por isso o push não pode ser feito pelo assistente.

### Não verificado
- **Service worker não registra no painel de prévia** (webview restrito). O
  código está escrito e o arquivo é servido corretamente, mas só se confirma
  em Chrome ou Safari de verdade.
- **O passo final do calendário depende do aparelho.** No iPhone o Calendário
  costuma abrir na hora; no Android o arquivo passa pela lista de downloads.
  Não existe endereço universal que force "abra o app de calendário" pela web.

### Sabidamente fora de alcance
- Datas de pagamento pós-sorteio não estão no bloco padrão de algumas páginas.
- Conferência automática de sorteio depende de o Sesc publicar a lista; hoje
  são 11 eventos com códigos coletados.

---

## 7. Como rodar

Só precisa de Python 3.9+. Nenhuma dependência externa. **Node não está
instalado nesta máquina.**

```bash
python coletor.py --de 2026-08-11 --ate 2026-10-09   # ~5 min
python detalhes.py --html                            # ~70 min (descrições)
python reparse.py                                    # instantâneo
python extras.py                                     # ~4 min (fotos + endereços)
python embutir.py --com-descricao                    # arquivo único
python publicar.py                                   # pasta web/
python -m http.server 8100 --directory web           # testar
```

Do celular na mesma Wi-Fi: `http://192.168.0.240:8100`

Opções úteis:

```bash
python detalhes.py --html --faltantes    # incremental, só os sem descrição
python embutir.py --sem-projeto          # tira temporadas e programas recorrentes
python embutir.py --horizonte 90         # muda a janela da retenção
python publicar.py --base /agenda-sesc/  # subpasta do GitHub Pages
```

---

## 8. Decisões de design

### 8.0 v4 — "Cartaz" (o design em vigor)

A v3 era **papel e tinta**: guia impresso, fios finos no lugar de cartões,
serifa nos títulos, sans na lista, monoespaçada nos dados, raio máximo 4px,
tema claro. Ela resolvia o volume — 2,3 mil eventos, 500 por dia — mas
escondia o que faz alguém escolher um espetáculo: **a foto**. O portal publica
uma imagem para cada atividade e o app jogava fora.

A v4 mantém a densidade e parte da foto. Três mudanças de fundo:

1. **A foto é o convite.** Cartão com imagem 16:9, linha da agenda com
   miniatura de 62px, folha de detalhe com capa sangrada e título por cima.
   Sem foto (12 de 1.320 no publicado), o lugar vira um cartaz desenhado com a
   tinta da categoria e a inicial do título — um retângulo cinza vazio se lê
   como falha de carregamento.
2. **As respostas viram etiqueta.** Três perguntas se repetem em toda decisão:
   *ainda dá para entrar* (Últimos ingressos / Esgotado), *é para mim*
   (Público) e *onde é* (Local). Viraram um componente só, `.tag`, com a mesma
   forma no cartão, na lista e no detalhe. Na linha densa o texto abrevia
   (`opc.curto`): sai o "a partir de" e o "Sesc", que não cabem em 185px.
3. **O filtro sai da gaveta.** Ver "Filtros" abaixo.

Tipografia: **Bricolage Grotesque** nos títulos (voz de cartaz, com caráter) e
**Archivo** no texto, com pilha de reserva do sistema — sem rede o app cai em
sans-serif e nada quebra de layout. Monoespaçada continua em hora e número.

Cor: papel morno (`#FAF8F4`), tinta quente quase preta, **um** azul de ação e
as oito tintas de categoria. A regra da v3 continua valendo — o cromo é
neutro, a cor pertence ao conteúdo — só que agora quem colore é a foto. Raio:
6px em controle, 12px em mídia e caixa, 20px na folha, pílula em botão e
etiqueta.

Os tokens estão no topo do CSS de `prototipo.html`. Trocar os valores desse
bloco reveste o app inteiro sem tocar em componente.

**"Para você" tem quatro trilhos, nesta ordem**, e cada um é uma pergunta:

1. Novidades na programação — o que é novo
2. Hoje e amanhã — o que dá para fazer agora
3. Agenda da semana — como está a semana
4. Inscrição ou venda abre em breve — do que cuidar antes que abra

A v3 tinha doze. A tela virava corredor e a mesma atividade aparecia em
quatro deles. Inscrição e venda viraram um trilho só porque, para quem lê, a
pergunta é uma só: *quando abre?* — separá-las obrigava a olhar os dois para
não perder nada. O trilho de novidades **não aparece** numa base sem o carimbo
`visto` (ver 4.5): ali ele seria permanentemente vazio na primeira dobra.

**Filtros.** Antes eram quatro lugares com quatro gramáticas: a barra de
contexto (unidades), a gaveta (projetos e categorias), a folha de unidades e a
fileira de chips da agenda. Quem tinha três filtros ligados não tinha onde ver
os três juntos, e desligar um exigia lembrar de onde tinha vindo.

Agora é um lugar só: uma **barra sempre visível** com o que está ligado, em
pastilha que se desliga com um toque, e uma **folha única** com região,
unidades (com busca), categorias, público, preço, situação da entrada e
projetos. As contagens continuam facetadas — cada opção é contada com todos os
outros filtros aplicados, **menos o dela própria**. Até três unidades aparecem
pelo nome na barra, porque "3 unidades" não diz se Pompeia está entre elas.

Consequência importante: a situação da entrada (grátis, com ingressos,
inscrição aberta, por sorteio…) **deixou de ser um chip só da agenda** e virou
faceta global — agora vale também nos trilhos e nas contagens.

**Duas colisões de nome que custaram depuração:**

- A miniatura da lista chamava-se `.mini` e a fileira compacta de etiquetas,
  `.tags.mini`. A regra `.ev .mini { width: 62px; height: 62px }` casava com as
  duas, e a fileira de etiquetas virava um quadrado de 62px: `Esg…`,
  `a parti…`, `Ses…`. A miniatura agora é `.thumb`.
- `regiaoDaUnidade()` era chamada em `abrirUnidades()` e **nunca existiu** —
  trocar a aba de região com unidades marcadas quebrava a folha inteira com
  `ReferenceError`. Bug antigo, exposto ao reaproveitar o código na folha de
  filtros. Definida.

### 8.1 Computador

O app nasceu para o celular — uma coluna de 460px — e numa tela larga isso vira
uma tira no meio de um deserto. A versão para computador é **só layout**: media
queries no fim do CSS, nenhum componente novo, nenhum caminho de código
separado. O celular não é tocado.

A escada de larguras:

| a partir de | o que muda |
|---|---|
| 900px | a gaveta vira coluna fixa à esquerda (286px), as abas do topo somem, a busca fica sempre visível, os trilhos viram grade de 2 colunas |
| 1100px | trilhos com 3 colunas |
| 1240px | trilhos com 4 colunas; a lista densa (agenda e favoritos) ganha **duas colunas**, com a faixa do dia atravessando as duas |

Decisões que valem registro:

- **A gaveta deixa de ser gaveta.** Com ela permanente, as abas do topo viram o
  mesmo menu duas vezes e saem (`.mainnav { display: none }`). Isso muda o
  grude da faixa de dia, que passa de 99px para 57px.
- **Os quatro destinos são a navegação, e precisam ter peso disso.** Na
  primeira versão eles ficaram com a aparência de item de menu do celular e
  não foram lidos como abas — o relato foi "faltou uma aba para cada opção".
  Agora têm corpo de aba: alvo de 42px, tipo maior, estado ativo em bloco
  cheio de tinta com marcador de cor, e contador à direita. Filtros,
  categorias e dados seguem em texto miúdo, para a hierarquia dizer o que é
  navegação e o que é ajuste.
- **Trilho vira grade, não carrossel.** Arrastar cartão com mouse é ruim. São
  sempre **duas fileiras** — o resto continua atrás de "ver todos", senão cada
  trilho viraria parede.
- **A folha de detalhe encosta à direita** em vez de subir do rodapé: numa tela
  larga, subir do fundo esconde o que a pessoa estava lendo. O véu começa em
  286px, então a coluna da esquerda continua clicável com a folha aberta.
- **O conteúdo para de crescer em 1180px.** Linha longa demais cansa tanto
  quanto lista longa demais.

O único JS envolvido é `ajustarModo()`, atrelado a um `matchMedia`: uma coluna à
vista não pode continuar marcada como `aria-hidden`, e o véu e a trava de
rolagem não fazem sentido nela.

**Armadilha ao testar:** o site publicado tem service worker, e ele guarda a
casca. Mudou o CSS e a tela não mudou? O SW está servindo o `index.html`
antigo — é preciso desregistrar e limpar o cache, não basta recarregar.

### 8.2 Calendário: o computador é outro bicho

No celular o alvo é o app de agenda do aparelho, e o `.ics` é o que o sistema
entende. No computador esse caminho não existe: o navegador baixa o arquivo e
ele morre na pasta de downloads — foi exatamente o "não acontece nada"
relatado. Por isso, no computador, aparece um botão **ao lado** do principal
para o **Google Agenda** (`calendar.google.com/render?action=TEMPLATE`), com
`ctz=America/Sao_Paulo` explícito: sem o fuso, o Google usa o da conta e quem
estiver fora do Brasil agenda na hora errada. E o aviso diz onde o arquivo foi
parar, senão "baixar" também parece "não aconteceu nada".

O que **saiu** na v4: a folha de escolha de calendário (app / Google / Outlook
/ baixar / escolher datas). Ela era uma tela inteira entre o toque e o
resultado, para uma decisão que quase sempre tem uma resposta só. O botão faz
o que diz; o resto é escolhido pelo contexto.

### 8.3 Como rodar o backfill de fotos e endereços

```bash
python extras.py            # fotos + públicos + endereços das 43 unidades
python extras.py --fotos    # só as fotos (quando muda o critério de tamanho)
python embutir.py --com-descricao
python publicar.py
```

O design system está no topo do CSS de `prototipo.html`, em tokens. Trocar os
valores desse bloco reveste o app inteiro sem tocar em componente.
