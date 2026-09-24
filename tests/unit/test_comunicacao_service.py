from app.services.comunicacao_service import rodape_email, validar_texto


def test_rodape_email_inclui_link_de_opt_out():
    """Extraído de `cadencia_service._rodape_por_canal` (raio-X
    2026-09-24, Webmail) — mesmo texto/formato de sempre."""
    resultado = rodape_email("tenant-teste", 1, "Olá, tudo bem?")

    assert resultado.startswith("Olá, tudo bem?\n\nPara não receber mais e-mails: ")
    assert "/opt-out/email/" in resultado


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
