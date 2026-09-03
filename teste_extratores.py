#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Testes dos extratores, sem rede.

O HANDOFF lista uma dúzia de armadilhas de extração já resolvidas, cada uma
com uma rodada de depuração atrás. Nenhuma tinha teste: a única verificação
era `teste_detalhes.py`, que busca cinco páginas na rede, imprime o resultado
e termina com sucesso aconteça o que acontecer — diagnóstico, não teste.

Aqui os textos são reais, tirados da coleta, e as asserções conferem o que
qualquer pessoa lendo o trecho concluiria. Roda em milissegundos e não toca
na rede, então serve para a CI.

    python teste_extratores.py
"""

import unittest

import detalhes

ANO = 2026


class DatasDeInscricao(unittest.TestCase):
    """`datas_do_texto` sobre trechos reais do portal."""

    def ler(self, texto, dia_evento="2026-09-02"):
        r = detalhes.datas_do_texto(texto, ANO, dia_evento)
        r.pop("texto", None)
        return r

    def test_inscricao_com_hora_e_sorteio(self):
        r = self.ler("Inscrições: 7/8 às 14h a 12/8 Sorteio: 13/8 às 15h "
                     "1ª chamada pagamento: 13 a 18/8 2ª chamada pagamento: 19 a 20/8")
        self.assertEqual(r["inscricao"], "2026-08-07T14:00")
        self.assertEqual(r["inscricaoFim"], "2026-08-12")
        self.assertEqual(r["sorteio"], "2026-08-13T15:00")
        self.assertTrue(r["temSorteio"])

    def test_intervalo_de_a_nao_inverte(self):
        """"Inscrições de 6 a 10/8" lia o FIM como início.

        O padrão era ancorado e falhava no "de ", então a primeira data que
        casava era a do fim.
        """
        r = self.ler("Inscrições de 2/7 a 7/7.")
        self.assertEqual(r["inscricao"], "2026-07-02", "o início é 2/7, não 7/7")
        self.assertEqual(r["inscricaoFim"], "2026-07-07")

    def test_para_o_sorteio_nao_vira_data_do_sorteio(self):
        """"Inscrição para o sorteio:" fazia o período virar data do sorteio.

        Resolvido com lookbehind. O trecho tem as duas coisas: a inscrição
        abre 6/8 e o resultado sai 14/8 — nunca o contrário.
        """
        r = self.ler("Inscrição para o sorteio: a partir das 14h do dia 6/8 até às "
                     "18h do dia 11/8. Divulgação dos contemplados: a partir das 14h "
                     "do dia 14/8. Confirmação de vagas e pagamento: 14 a 18/8.",
                     dia_evento="2026-09-19")
        self.assertEqual(r["inscricao"], "2026-08-06")
        self.assertEqual(r["inscricaoFim"], "2026-08-11")
        self.assertEqual(r["sorteio"], "2026-08-14")
        self.assertNotEqual(r["sorteio"], r["inscricao"])

    def test_divulgacao_dos_sorteados_sem_dois_pontos(self):
        """Cabeçalhos alternativos do resultado, sem "Sorteio:"."""
        r = self.ler("Inscrições: dia 18/8, a partir das 14h, até 20/8, às 14h "
                     "Divulgação dos sorteados: dia 25/8, às 14h "
                     "Datas para pagamento: dias 27 e 28/8",
                     dia_evento="2026-09-12")
        self.assertEqual(r["sorteio"], "2026-08-25T14:00")
        self.assertEqual(r["inscricao"], "2026-08-18")
        self.assertEqual(r["pagamento"], "2026-08-27")

    def test_inscricao_no_singular_com_til(self):
        """"Inscrição" tem ã; o padrão exigia [õo] e nunca casava.

        Corrigiu 78 eventos quando foi achado.
        """
        r = self.ler("Inscrição: 5/8 às 10h.")
        self.assertEqual(r.get("inscricao"), "2026-08-05T10:00")


class RegrasRecorrentes(unittest.TestCase):
    """`regras_de_inscricao`: a extração mais delicada do projeto.

    São duas datas diferentes para duas pessoas diferentes, e nenhuma existe
    como data em lugar nenhum da fonte. Errar aqui manda alguém ao Sesc no
    dia em que não pode se inscrever.
    """

    CANONICO = ("As vagas disponíveis são liberadas prioritariamente para pessoas "
                "portadoras de Credencial Plena na 1ª e na 3ª quinta-feira de cada mês "
                "a partir das 18h. Caso estas vagas não sejam preenchidas, serão "
                "disponibilizadas para o público em geral na 2ª e na 4ª quarta-feira "
                "a partir das 14h.")

    def test_extrai_as_duas_janelas(self):
        """O caso do HANDOFF, que na prática só entregava uma.

        A segunda oração não repete "de cada mês", e o padrão exigia o sufixo
        em toda ocorrência — então a janela do público geral não existia.
        Medido na base: os 5 eventos com regra tinham 1 janela cada, todas
        "plena". Quem não tem credencial via a data que não era dele.
        """
        rs = detalhes.regras_de_inscricao(self.CANONICO)
        self.assertEqual(len(rs), 2, "faltou a janela do público geral")
        plena = [r for r in rs if r["quem"] == "plena"][0]
        geral = [r for r in rs if r["quem"] == "geral"][0]
        self.assertEqual(plena, {"quem": "plena", "semanas": [1, 3], "dow": 4, "hora": "18:00"})
        self.assertEqual(geral, {"quem": "geral", "semanas": [2, 4], "dow": 3, "hora": "14:00"})

    def test_publico_declarado_depois_da_regra(self):
        """"…a partir das 18h, para quem possui credencial plena".

        Ler só para trás fazia esta forma virar "todos", e com isso quem não
        tem credencial via uma data que não era dele.
        """
        rs = detalhes.regras_de_inscricao(
            "As vagas são liberadas na 1ª e 3ª quinta-feira de cada mês, a partir "
            "das 18h, para quem possui credencial plena.")
        self.assertEqual([r["quem"] for r in rs], ["plena"])

    def test_ordinal_por_extenso_nao_vira_data(self):
        """"primeira e segunda quinta-feira": "segunda" é ordinal e dia.

        Ler por extenso daria data errada, que é pior do que não dar data.
        """
        self.assertIsNone(detalhes.regras_de_inscricao(
            "Vagas liberadas na primeira e segunda quinta-feira de cada mês "
            "a partir das 18h."))

    def test_texto_solto_nao_vira_regra(self):
        """A forma sem "de cada mês" só vale acompanhando uma que o tenha.

        Sem esta trava, "a 1ª sexta-feira do festival, a partir das 20h"
        viraria regra de inscrição.
        """
        self.assertIsNone(detalhes.regras_de_inscricao(
            "O festival abre na 1ª sexta-feira, a partir das 20h, com show."))

    def test_sem_hora_nao_vira_regra(self):
        """Sem hora não há janela: metade da informação é pior que nenhuma."""
        self.assertIsNone(detalhes.regras_de_inscricao(
            "As vagas são liberadas na 1ª quinta-feira de cada mês."))


class ListaDeContemplados(unittest.TestCase):
    """`sorteados_do_corpo`: quatro cabeçalhos, e prosa que os imita."""

    def test_prosa_nao_vira_lista(self):
        """"os sorteados poderão efetivar o pagamento" não traz código.

        A trava é exigir código nos dois primeiros tokens depois do
        cabeçalho, o que em prosa nunca acontece.
        """
        self.assertFalse(detalhes.sorteados_do_corpo(
            "Os sorteados poderão efetivar o pagamento na Central de "
            "Atendimento a partir do dia 14/8, mediante apresentação de "
            "documento com foto."))

    def test_cabecalho_seco_com_codigos(self):
        """"CONTEMPLADOS" sozinho, logo depois de "Compartilhe:"."""
        achado = detalhes.sorteados_do_corpo(
            "Compartilhe: CONTEMPLADOS YDYNALVB WDSOMKPL QRTZAABC MNOPQRST")
        self.assertTrue(achado, "cabeçalho seco não foi reconhecido")
        self.assertIn("YDYNALVB", achado)


class LimpezaDeTexto(unittest.TestCase):
    def test_script_nao_vaza_para_a_descricao(self):
        """As tags saíam e o código ficava, indo parar na descrição."""
        sujo = ("<p>Uma peça sobre memória.</p>"
                "<script>var x = 1; alert('oi');</script>"
                "<style>.a{color:red}</style>")
        limpo = detalhes.limpar(sujo)
        for vazamento in ("var x", "alert", "color:red"):
            self.assertNotIn(vazamento, limpo)
        self.assertIn("memória", limpo)


if __name__ == "__main__":
    unittest.main(verbosity=2)
