from app.models.mensagem import Mensagem
from app.services import rastreamento_service

TENANT_ID = "tenant-teste"


def _criar_mensagem_enviada(db_session, decisor_id: int) -> Mensagem:
    mensagem = Mensagem(
        tenant_id=TENANT_ID,
        decisor_id=decisor_id,
        canal="email",
        conteudo="Ola",
        status="enviado",
    )
    db_session.add(mensagem)
    db_session.commit()
    return mensagem


def test_token_adulterado_nao_valida(db_session, criar_conta_com_decisor):
    conta, decisor = criar_conta_com_decisor()
    mensagem = _criar_mensagem_enviada(db_session, decisor.id)
    token = rastreamento_service.gerar_token_abertura(TENANT_ID, mensagem.id)
    token_adulterado = token[:-1] + ("0" if token[-1] != "0" else "1")

    rastreamento_service.registrar_abertura(db_session, token_adulterado)

    db_session.refresh(mensagem)
    assert mensagem.aberto_em is None


def test_registrar_abertura_marca_primeira_vez(db_session, criar_conta_com_decisor):
    conta, decisor = criar_conta_com_decisor()
    mensagem = _criar_mensagem_enviada(db_session, decisor.id)
    token = rastreamento_service.gerar_token_abertura(TENANT_ID, mensagem.id)

    rastreamento_service.registrar_abertura(db_session, token)

    db_session.refresh(mensagem)
    assert mensagem.aberto_em is not None


def test_registrar_abertura_nao_sobrescreve_a_primeira(db_session, criar_conta_com_decisor):
    conta, decisor = criar_conta_com_decisor()
    mensagem = _criar_mensagem_enviada(db_session, decisor.id)
    token = rastreamento_service.gerar_token_abertura(TENANT_ID, mensagem.id)

    rastreamento_service.registrar_abertura(db_session, token)
    db_session.refresh(mensagem)
    primeira_abertura = mensagem.aberto_em

    rastreamento_service.registrar_abertura(db_session, token)
    db_session.refresh(mensagem)

    assert mensagem.aberto_em == primeira_abertura
