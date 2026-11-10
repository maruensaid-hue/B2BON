"""Texto da IA sai sem cabeçalho de metadados nem markdown (tarefas de LinkedIn copiavam tudo junto, produção 10/11/2026)."""

from app.services.cadencia_service import limpar_texto_gerado


def test_tira_cabecalho_de_rotulos_e_separador():
    texto = (
        "**Canal:** LinkedIn (mensagem direta)\n**Toque:** 5 — Cadência de prospecção\n"
        "**Lead:** Marcelo Tavarone — Diretor comercial, 4Asset\n**Lista:** Importação LinkedIn\n\n---\n\n"
        "Marcelo, tentei falar por aqui algumas vezes."
    )
    assert limpar_texto_gerado(texto) == "Marcelo, tentei falar por aqui algumas vezes."


def test_tira_titulo_e_rotulo_mensagem():
    texto = (
        "# Toque 5 — LinkedIn (Cadência de Prospecção)\n**Contato:** Ralf — Auditor\n**Empresa:** Bulletproof\n\n---\n\n"
        "**Mensagem:**\n\nRalf, acho que não encontrei o momento certo."
    )
    assert limpar_texto_gerado(texto) == "Ralf, acho que não encontrei o momento certo."


def test_tira_titulo_em_negrito_e_negrito_no_meio():
    texto = "**Toque 4 — LinkedIn**\n\nLisiane, vejo que o **MAP** ajuda nisso."
    assert limpar_texto_gerado(texto) == "Lisiane, vejo que o MAP ajuda nisso."


def test_nao_mexe_em_texto_limpo_nem_em_primeira_linha_que_comeca_com_palavra_parecida():
    assert limpar_texto_gerado("Olá Ana,\n\nContato rápido sobre a prospecção.") == "Olá Ana,\n\nContato rápido sobre a prospecção."
    assert limpar_texto_gerado("Empresas como a sua costumam perder follow-up.") == "Empresas como a sua costumam perder follow-up."


def test_lista_com_hifen_e_preservada():
    texto = "Olá Ana,\n\n- Diminuir custo;\n- Aumentar resposta."
    assert limpar_texto_gerado(texto) == texto
