import pytest

from app.services import resposta_service
from app.services.errors import ValidacaoFalhou


def test_gerar_e_validar_token_resposta_ida_e_volta():
    token = resposta_service.gerar_token_resposta("tenant-teste", 42)

    tenant_id, decisor_id = resposta_service.validar_token_resposta(token)

    assert tenant_id == "tenant-teste"
    assert decisor_id == 42


def test_validar_token_resposta_adulterado_falha():
    token = resposta_service.gerar_token_resposta("tenant-teste", 42)
    token_adulterado = token[:-1] + ("0" if token[-1] != "0" else "1")

    with pytest.raises(ValidacaoFalhou):
        resposta_service.validar_token_resposta(token_adulterado)


def test_validar_token_resposta_formato_invalido_falha():
    with pytest.raises(ValidacaoFalhou):
        resposta_service.validar_token_resposta("token-sem-o-formato-certo")


def test_token_resposta_nao_usa_separador_dois_pontos():
    """Diferente de `optout_service.gerar_token` — precisa ser seguro
    como local-part de e-mail (`resp+{token}@dominio`)."""
    token = resposta_service.gerar_token_resposta("tenant-teste", 1)

    assert ":" not in token
    assert "@" not in token
