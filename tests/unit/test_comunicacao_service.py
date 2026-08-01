from app.services.comunicacao_service import validar_texto


def test_validar_texto_detecta_restricao_violada():
    violacoes = validar_texto(
        "Garantimos resultado em 30 dias ou seu dinheiro de volta.",
        restricoes=["garantimos resultado", "dinheiro de volta"],
    )

    assert violacoes == ["garantimos resultado", "dinheiro de volta"]


def test_validar_texto_sem_violacao_retorna_lista_vazia():
    violacoes = validar_texto(
        "Podemos ajudar sua empresa a organizar o processo comercial.",
        restricoes=["garantimos resultado"],
    )

    assert violacoes == []


def test_validar_texto_e_case_insensitive():
    violacoes = validar_texto("GARANTIMOS o melhor preço do mercado.", restricoes=["garantimos"])

    assert violacoes == ["garantimos"]
