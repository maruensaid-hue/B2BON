import hashlib

import pytest

from app.api.deps import get_chave_api_atual
from app.models.chave_api_parceiro import ChaveApiParceiro
from app.models.tenant import Tenant
from app.services.errors import NaoAutenticado

CHAVE_COMPLETA = "b2bon_chave-de-teste-bem-secreta"


def _criar_chave(db_session, revogada: bool = False) -> ChaveApiParceiro:
    db_session.add(Tenant(id="distribuidor-deps", razao_social="Distribuidor Deps", tipo="distribuidor"))
    db_session.flush()
    chave = ChaveApiParceiro(
        tenant_id="distribuidor-deps",
        nome="Chave Teste",
        prefixo=CHAVE_COMPLETA[:12],
        chave_hash=hashlib.sha256(CHAVE_COMPLETA.encode()).hexdigest(),
    )
    if revogada:
        from datetime import UTC, datetime

        chave.revogada_em = datetime.now(UTC)
    db_session.add(chave)
    db_session.commit()
    return chave


def test_chave_valida_retorna_registro_e_atualiza_ultimo_uso(db_session) -> None:
    chave_criada = _criar_chave(db_session)
    assert chave_criada.ultimo_uso_em is None

    resultado = get_chave_api_atual(authorization=f"Bearer {CHAVE_COMPLETA}", db=db_session)

    assert resultado.id == chave_criada.id
    assert resultado.ultimo_uso_em is not None


def test_sem_header_authorization_levanta_nao_autenticado(db_session) -> None:
    with pytest.raises(NaoAutenticado):
        get_chave_api_atual(authorization=None, db=db_session)


def test_header_sem_bearer_levanta_nao_autenticado(db_session) -> None:
    with pytest.raises(NaoAutenticado):
        get_chave_api_atual(authorization=CHAVE_COMPLETA, db=db_session)


def test_chave_invalida_levanta_nao_autenticado(db_session) -> None:
    _criar_chave(db_session)

    with pytest.raises(NaoAutenticado):
        get_chave_api_atual(authorization="Bearer chave-que-nao-existe", db=db_session)


def test_chave_revogada_levanta_nao_autenticado(db_session) -> None:
    _criar_chave(db_session, revogada=True)

    with pytest.raises(NaoAutenticado):
        get_chave_api_atual(authorization=f"Bearer {CHAVE_COMPLETA}", db=db_session)
