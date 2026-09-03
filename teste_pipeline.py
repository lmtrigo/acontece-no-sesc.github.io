#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Testes de regressão do pipeline e da casca do app.

Por que este arquivo existe: o rastreio de novidades foi desligado por uma
mudança que nada tinha a ver com ele — `dados/eventos.json` deixou de ser
versionado para o repositório parar de crescer, e com isso o coletor passou a
não achar a coleta anterior. O recurso sumiu do app e o pipeline continuou
terminando com sucesso, imprimindo uma linha informativa.

A lição não é "aquele bug": é que toda verificação deste projeto era manual.
O que está aqui são as invariantes que, quebradas, não gritam sozinhas.

    python teste_pipeline.py

Sem dependências externas. O que precisa de rede ou de uma coleta no disco é
pulado com a razão dita em voz alta, para "pulou" nunca se confundir com
"passou".
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

RAIZ = os.path.dirname(os.path.abspath(__file__))
PROTOTIPO = os.path.join(RAIZ, "prototipo.html")
WORKFLOW = os.path.join(RAIZ, ".github", "workflows", "atualizar.yml")
BASE = os.path.join(RAIZ, "dados", "eventos.json")


def ler(caminho):
    with open(caminho, encoding="utf-8") as f:
        return f.read()


def css_de(html):
    """O bloco <style> do app, onde vivem os tokens."""
    return html[html.index("<style>"):html.index("</style>")]


def js_de(html):
    """O último <script> do app — o IIFE inteiro."""
    ini = html.rindex("<script>") + len("<script>")
    return html[ini:html.rindex("</script>")]


def luminancia(hexa):
    h = hexa.lstrip("#")
    canais = []
    for i in (0, 2, 4):
        c = int(h[i:i + 2], 16) / 255
        canais.append(c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4)
    return 0.2126 * canais[0] + 0.7152 * canais[1] + 0.0722 * canais[2]


def contraste(a, b):
    l1, l2 = sorted((luminancia(a), luminancia(b)), reverse=True)
    return (l1 + 0.05) / (l2 + 0.05)


def tokens_do_bloco(css, seletor):
    """Os pares --nome: #RRGGBB do primeiro bloco que casa com `seletor`."""
    i = css.index(seletor)
    corpo = css[i:css.index("}", i)]
    return dict(re.findall(r"(--[\w-]+):\s*(#[0-9A-Fa-f]{6})", corpo))


# ---------------------------------------------------------------- rastreio
class RastreioDeNovidades(unittest.TestCase):
    """O caso que motivou o arquivo.

    `carimbar_estreia` é a função inteira do recurso "Novidades", e ela falha
    para o lado silencioso: sem base anterior, devolve linha de base e segue.
    """

    def setUp(self):
        sys.path.insert(0, RAIZ)
        import coletor
        self.coletor = coletor
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _gravar(self, nome, dados):
        caminho = os.path.join(self.tmp, nome)
        with open(caminho, "w", encoding="utf-8") as f:
            json.dump(dados, f)
        return caminho

    def test_com_base_anterior_preserva_o_carimbo(self):
        anterior = self._gravar("ant.json", {
            "rastreioDesde": "2026-08-01",
            "eventos": [{"id": "a", "visto": "2026-08-10"}, {"id": "b"}],
        })
        lista = [{"id": "a"}, {"id": "b"}, {"id": "c"}]
        desde = self.coletor.carimbar_estreia(lista, anterior, "2026-09-03")

        self.assertEqual(desde, "2026-08-01", "rastreioDesde não pode reiniciar")
        por_id = {e["id"]: e for e in lista}
        self.assertEqual(por_id["a"].get("visto"), "2026-08-10",
                         "quem já estava conserva a data antiga")
        self.assertIsNone(por_id["b"].get("visto"),
                          "quem é anterior ao rastreio fica sem carimbo")
        self.assertEqual(por_id["c"].get("visto"), "2026-09-03",
                         "quem não estava na anterior é novidade de hoje")

    def test_sem_base_anterior_nao_carimba_ninguem(self):
        """Comportamento correto — e exatamente por isso perigoso.

        Não marcar tudo como novo está certo. O problema é isto acontecer
        todo dia sem ninguém perceber, e é o workflow que tem de impedir.
        """
        lista = [{"id": "a"}, {"id": "b"}]
        desde = self.coletor.carimbar_estreia(
            lista, os.path.join(self.tmp, "nao_existe.json"), "2026-09-03")
        self.assertEqual(desde, "2026-09-03")
        self.assertFalse(any(e.get("visto") for e in lista))

    def test_workflow_garante_a_base_anterior(self):
        """O teste que teria pego o erro.

        Não basta a função estar certa: alguém tem de entregar a base de
        ontem antes de o coletor rodar. Se este teste falhar, o recurso
        "Novidades" morre em silêncio na próxima execução.
        """
        wf = ler(WORKFLOW)
        antes_do_coletor = wf[:wf.index("python coletor.py")]
        tem_cache = "actions/cache" in antes_do_coletor
        tem_queda = "dados/eventos.json" in antes_do_coletor and "curl" in antes_do_coletor
        self.assertTrue(
            tem_cache or tem_queda,
            "nada restaura dados/eventos.json antes do coletor: sem a coleta "
            "anterior, carimbar_estreia zera o rastreio a cada execução")

    def test_base_no_disco_tem_rastreio(self):
        if not os.path.exists(BASE):
            self.skipTest("sem dados/eventos.json local (rode o coletor)")
        d = json.loads(ler(BASE))
        self.assertIn("rastreioDesde", d,
                      "a base gravada precisa carregar o próprio marco de rastreio")


# ------------------------------------------------------- fonte x publicado
class FonteEnxuta(unittest.TestCase):
    """O arquivo-fonte não pode voltar a carregar o instantâneo.

    Ele já pesou 4,9 MB e entrava inteiro no histórico do git a cada coleta.
    `embutir.py` grava em previa.html; `publicar.py` gera web/.
    """

    def setUp(self):
        self.html = ler(PROTOTIPO)

    def test_marcadores_de_dados_presentes(self):
        # embutir.py e publicar.py recortam por estes marcadores; sem eles,
        # os dois falham — e publicar.py falha depois de uma hora de coleta
        self.assertIn("/* DADOS:INICIO */", self.html)
        self.assertIn("/* DADOS:FIM */", self.html)

    def test_fonte_sem_instantaneo(self):
        ini = self.html.index("/* DADOS:INICIO */")
        fim = self.html.index("/* DADOS:FIM */")
        embutido = self.html[ini:fim]
        self.assertLess(len(embutido), 4096,
                        "prototipo.html voltou a carregar dados embutidos: "
                        "rode `python embutir.py`, que grava em previa.html")

    def test_fonte_sem_script_de_medicao(self):
        """Medir o teste local sujaria o painel com os nossos próprios acessos."""
        self.assertNotIn("data-goatcounter", self.html,
                         "o contador entra só na saída publicada, em publicar.py")

    def test_gitignore_protege_os_gerados(self):
        ig = ler(os.path.join(RAIZ, ".gitignore"))
        for alvo in ("previa.html", "dados/eventos.json", "web/"):
            self.assertIn(alvo, ig, "%s precisa ficar fora do git" % alvo)


# ------------------------------------------------------------- design v4.1
class TokensDeCor(unittest.TestCase):
    """Contraste é a única parte do desenho que se verifica por conta.

    O cinza secundário já reprovou uma vez (3,51:1) e ninguém viu por meses.
    E a paleta noturna nasceu errada: foi medida contra o papel quando o
    texto vive no cartão, que é mais claro.
    """

    def setUp(self):
        self.css = css_de(ler(PROTOTIPO))

    def _conferir(self, seletor, nome_tema):
        t = tokens_do_bloco(self.css, seletor)
        fundo = t.get("--surface")
        self.assertIsNotNone(fundo, "%s sem --surface" % nome_tema)
        alvos = [k for k in t if k.startswith("--cat-")]
        alvos += ["--ink-3", "--ink-2", "--accent", "--pos", "--warn", "--neg"]
        ruins = []
        for k in alvos:
            if k not in t:
                continue
            r = contraste(t[k], fundo)
            if r < 4.5:
                ruins.append("%s %s = %.2f:1" % (k, t[k], r))
        self.assertEqual(ruins, [],
                         "%s: tinta abaixo de 4,5:1 sobre --surface (%s): %s"
                         % (nome_tema, fundo, ", ".join(ruins)))

    def test_tema_claro_passa_em_aa(self):
        self._conferir(":root {", "tema claro")

    def test_tema_escuro_passa_em_aa(self):
        self._conferir(':root[data-tema="escuro"]', "tema escuro")

    def test_escala_de_tipo_em_rem(self):
        """Em px, a preferência de fonte grande do sistema não tem efeito."""
        sobraram = re.findall(r"font-size:\s*([\d.]+)px", self.css)
        self.assertEqual(sobraram, [],
                         "font-size em px voltou ao CSS: %s" % sobraram)


# ------------------------------------------------------------ casca do app
class CascaDoApp(unittest.TestCase):
    def setUp(self):
        self.html = ler(PROTOTIPO)
        self.js = js_de(self.html)

    def test_js_sem_erro_de_sintaxe(self):
        """Um erro aqui mata o app inteiro, e o HTML continua servindo bem.

        Node não está instalado nesta máquina, mas está nos runners do
        GitHub — então na CI este teste roda de verdade.
        """
        node = shutil.which("node")
        if not node:
            self.skipTest("node ausente (roda na CI)")
        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False,
                                         encoding="utf-8") as f:
            f.write(self.js)
            temp = f.name
        try:
            p = subprocess.run([node, "--check", temp],
                               capture_output=True, text=True)
            self.assertEqual(p.returncode, 0, p.stderr)
        finally:
            os.unlink(temp)

    def test_sem_marca_combinante_literal_no_js(self):
        """A classe /[\\u0300-\\u036f]/ do normalizador de acento.

        Escrita com os caracteres combinantes de verdade em vez das escapes,
        ela vira uma faixa inválida e derruba o script inteiro. Já aconteceu
        duas vezes ao editar o arquivo por script.
        """
        achadas = re.findall(r"[̀-ͯ]", self.js)
        self.assertEqual(achadas, [],
                         "marca combinante literal no JS: use \\u0300-\\u036f")

    def test_esconder_item_de_menu_funciona(self):
        """`.ditem` define display:flex, que vence o [hidden] do navegador.

        Sem a regra explícita, esconder pelo atributo não surte efeito e
        "Meus Sorteios" fica na tela com zero sorteios guardados.
        """
        css = css_de(self.html)
        self.assertRegex(
            css, r"\.ditem\[hidden\][^{]*\{[^}]*display:\s*none",
            "falta `.ditem[hidden] { display: none }`: o atributo perde para "
            "o display do próprio componente")

    def test_medicao_nao_derruba_o_app(self):
        i = self.js.index("function medir(")
        corpo = self.js[i:self.js.index("\n  }", i)]
        self.assertIn("catch", corpo, "medir() precisa engolir o próprio erro")


# ------------------------------------------------------------- publicação
class Publicacao(unittest.TestCase):
    """Invariantes da pasta web/, quando ela existe."""

    def setUp(self):
        self.web = os.path.join(RAIZ, "web")
        if not os.path.isdir(self.web):
            self.skipTest("sem web/ (rode `python publicar.py`)")
        self.index = ler(os.path.join(self.web, "index.html"))

    def test_publicado_sem_instantaneo(self):
        tamanho = os.path.getsize(os.path.join(self.web, "index.html"))
        self.assertLess(tamanho, 600 * 1024,
                        "web/index.html com %d KB: o instantâneo voltou, e a "
                        "primeira carga triplica" % (tamanho // 1024))

    def test_publicado_tem_medicao(self):
        self.assertIn("data-goatcounter", self.index)
        self.assertIn("https://gc.zgo.at/count.js", self.index,
                      "endereço relativo a protocolo vira http:// e falha")

    def test_pwa_completo(self):
        for nome in ("manifest.webmanifest", "sw.js", "icon-192.png",
                     "icon-512.png", "dados/eventos.json"):
            self.assertTrue(os.path.exists(os.path.join(self.web, nome)),
                            "web/%s não foi gerado" % nome)

    def test_service_worker_versiona_pela_casca(self):
        """O nome do cache precisa mudar quando o app muda.

        Quando era o carimbo da coleta, mexer no CSS entre duas coletas não
        trocava o nome e quem já tinha instalado nunca via a mudança.
        """
        sw = ler(os.path.join(self.web, "sw.js"))
        versao = re.search(r"VERSAO\s*=\s*'([^']+)'", sw)
        self.assertIsNotNone(versao, "sw.js sem VERSAO")
        self.assertRegex(versao.group(1), r"[0-9a-f]{12}",
                         "VERSAO precisa derivar do sha1 do index.html")


if __name__ == "__main__":
    unittest.main(verbosity=2)
