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

**Armadilha conhecida:** o filtro de data **omite eventos**. "Ecos da
Independência" (12/09) não volta na consulta de 12/09, mas aparece na listagem
sem filtro. Por isso `coletor.py` faz uma varredura geral depois do dia a dia —
recuperou 53 eventos, 25 deles Turismo Social.

### 2.2 Regiões das unidades

```
GET https://www.sescsp.org.br/wp-json/wp/v1/unidades-atividades
```

O campo `description` já traz `capital` | `interior` | `litoral`. São 43
unidades: 25 capital, 16 interior, 2 litoral.

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
- Fim da página, após "Resultado do Sorteio:" → códigos contemplados
- Descrição → texto entre "Compartilhe:" e o primeiro bloco de serviço

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

## 5. Arquitetura

```
coletor.py   → dados/eventos.json          (listagem, dia a dia + varredura)
detalhes.py  → enriquece o mesmo arquivo   (bilheteria + HTML)
reparse.py   → reprocessa sem rede         (usa o texto já guardado)
embutir.py   → prototipo.html              (arquivo único, prévia por link)
publicar.py  → web/                        (site hospedável, PWA)
```

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

### 5.3 Calendário

**Um `blob:` nunca abre o app de calendário** — não tem endereço que o sistema
reconheça, então o navegador sempre trata como download. O que funciona é um
`.ics` servido por **URL real** com `Content-Type: text/calendar`.

`publicar.py` gera: um `.ics` por evento (viagem = intervalo único com
`DTEND` exclusivo), um por sessão para eventos com até 8 datas, e um da
abertura da inscrição. Total ~5.900 arquivos.

O **service worker reescreve o Content-Type** para `text/calendar`: nem todo
host declara esse tipo (o `http.server` do Python manda
`application/octet-stream`) e sem isso o celular não entrega ao app de agenda.

---

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

Direção **papel e tinta**: guia de programação impresso. Fios finos no lugar de
cartões, serifa nos títulos de seção e da folha de detalhe, sans na lista
(serifa em lista longa vira textura), monoespaçada nos dados. Raio máximo 4px.
Tema claro por decisão de projeto.

**A cor pertence ao conteúdo**: o cromo é preto-e-papel, e o único colorido é a
categoria do evento. Sete tintas separadas no círculo cromático, escolhidas para
não evocar a marca do Sesc.

Arquitetura de informação: **contexto antes de catálogo**. Na primeira abertura
o app pergunta as unidades — isso corta o universo de 2.119 para ~100. A home
responde perguntas em trilhos ("Inscrição abre em breve", "Grátis no fim de
semana"), e a agenda é lista densa com hora na goteira.

O design system está no topo do CSS de `prototipo.html`, em tokens. Trocar os
valores desse bloco reveste o app inteiro sem tocar em componente.
