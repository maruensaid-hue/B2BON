import pytest

from app.core.texto import corrigir_codificacao


@pytest.mark.parametrize(
    "corrompido, esperado",
    [
        ("JoÃ£o Paulo Nieto", "João Paulo Nieto"),
        ("Jéssica".encode("utf-8").decode("latin-1"), "Jéssica"),
        ("Grupo BoticÃ¡rio", "Grupo Boticário"),
        ("SND DistribuiÃ§Ã£o", "SND Distribuição"),
        ("Autônomo".encode("utf-8").decode("latin-1"), "Autônomo"),
        # Windows-1252: aspas, travessões e letras maiúsculas acentuadas usam caracteres que o Latin-1 não tem
        ("ValCity â€” Consultoria e ServiÃ§os", "ValCity — Consultoria e Serviços"),
        ("AGK CORRETORA DE CÃ‚MBIO S.A.", "AGK CORRETORA DE CÂMBIO S.A."),
        ("UNICRED ESTADO DE SÃƒO PAULO", "UNICRED ESTADO DE SÃO PAULO"),
        ("Marcus CADIDÃ‰", "Marcus CADIDÉ"),
    ],
)
def test_conserta_texto_com_a_codificacao_trocada(corrompido, esperado):
    assert corrigir_codificacao(corrompido) == esperado


@pytest.mark.parametrize(
    "texto",
    [
        "João Paulo",
        "SÃO PAULO",
        "CÂMBIO Ltda",
        "José Souza",
        "Telefônica Brasil",
        "Soluções 🇧🇷",
        "Texto normal",
        "",
    ],
)
def test_texto_correto_passa_intacto(texto):
    assert corrigir_codificacao(texto) == texto


def test_byte_perdido_na_copia_deixa_o_texto_como_veio():
    assert corrigir_codificacao("Dâ€™Ãvila") == "Dâ€™Ãvila"  # o "Á" perdeu um byte invisível: não dá para reconstruir com segurança


def test_vazio_e_nulo():
    assert corrigir_codificacao(None) is None
    assert corrigir_codificacao("") == ""
