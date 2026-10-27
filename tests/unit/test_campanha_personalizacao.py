import pytest

from app.services.campanha_personalizacao import primeiro_nome, renderizar


@pytest.mark.parametrize(
    "nome, esperado",
    [
        ("Maria da Silva", "Maria"),
        ("MARIA DA SILVA", "Maria"),
        ("joão pereira", "João"),
        ("Dra. ana lima", "Ana"),
        ("Sr. Carlos", "Carlos"),
        ("McDonald Silva", "McDonald"),
        ("  ", ""),
        (None, ""),
    ],
)
def test_primeiro_nome(nome, esperado):
    assert primeiro_nome(nome) == esperado


def test_troca_nome_e_empresa_pelos_dados_do_cadastro():
    texto = "Olá, [Nome],\n\nVi que a [Empresa] está crescendo."
    assert renderizar(texto, "Maria da Silva", "Acme") == "Olá, Maria,\n\nVi que a Acme está crescendo."


def test_marcadores_ignoram_maiusculas_e_espacos_dentro_dos_colchetes():
    assert renderizar("[NOME] e [ empresa ] e [nome completo]", "Ana Lima", "Acme") == "Ana e Acme e Ana Lima"


def test_sem_nome_a_saudacao_fica_so_com_o_ola():
    assert renderizar("Olá, [Nome],\n\nTexto.", None, "Acme") == "Olá!\n\nTexto."
    assert renderizar("Olá, [Nome]!\nTexto.", "", "Acme") == "Olá!\nTexto."
    assert renderizar("Olá [nome],\nTexto.", "  ", None) == "Olá!\nTexto."
    assert renderizar("Olá, [Nome]\nTexto.", None, None) == "Olá!\nTexto."
    assert renderizar("Olá, [Nome]", None, None) == "Olá!"
    assert renderizar("Olá, [Nome], tudo bem?", None, None) == "Olá! tudo bem?"


def test_sem_nome_no_meio_da_frase_nao_cola_as_palavras():
    assert renderizar("Falei com [Nome] ontem", None, None) == "Falei com ontem"


def test_sem_empresa_entra_a_sua_empresa():
    assert renderizar("Uma proposta para [Empresa].", "Ana", None) == "Uma proposta para a sua empresa."
    assert renderizar("Uma proposta para [Empresa].", "Ana", "  ") == "Uma proposta para a sua empresa."


def test_texto_sem_marcadores_e_valores_com_caracteres_especiais_passam_intactos():
    assert renderizar("Sem marcador.", "Ana", "Acme") == "Sem marcador."
    assert renderizar("[Empresa]", "Ana", r"A\1 & B [Nome]") == r"A\1 & B [Nome]"
    assert renderizar(None, "Ana", "Acme") == ""
