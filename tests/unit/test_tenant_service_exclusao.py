from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select

from app.db.base import Base
from app.models.auditoria import AuditLog
from app.models.campo_enriquecido import CampoEnriquecido
from app.models.chave_api_parceiro import ChaveApiParceiro
from app.models.conta import Conta
from app.models.decisor import Decisor
from app.models.estagio_funil import EstagioFunil
from app.models.licenca import Licenca
from app.models.negocio import Negocio
from app.models.pagamento_licenca import PagamentoLicenca
from app.models.plano import Plano
from app.models.registro_supressao_permanente import RegistroSupressaoPermanente
from app.models.tenant import Tenant
from app.models.usuario import Usuario
from app.services import tenant_service
from app.services.errors import NaoAutorizado, RegraNegocioViolada

TENANT_ATUANTE = "tenant-operador"
TENANT_ALVO = "tenant-alvo"


def _ator(db_session, papel: str = "super_admin", tenant_id: str = TENANT_ATUANTE) -> Usuario:
    if db_session.query(Tenant).filter_by(id=tenant_id).one_or_none() is None:
        db_session.add(Tenant(id=tenant_id, razao_social=f"Empresa {tenant_id}"))
        db_session.flush()
    usuario = Usuario(tenant_id=tenant_id, nome="Ator", email=f"ator-{tenant_id}@teste.com", papel=papel, ativo=True)
    db_session.add(usuario)
    db_session.commit()
    return usuario


def _tenant_alvo(db_session, tenant_id: str = TENANT_ALVO, tenant_pai_id: str | None = None) -> Tenant:
    tenant = Tenant(id=tenant_id, razao_social=f"Empresa {tenant_id}", tenant_pai_id=tenant_pai_id)
    db_session.add(tenant)
    db_session.commit()
    return tenant


def test_desativar_bloqueia_com_tenant_filho(db_session):
    ator = _ator(db_session)
    _tenant_alvo(db_session, "pai-com-filho")
    _tenant_alvo(db_session, "filho-de-pai", tenant_pai_id="pai-com-filho")

    with pytest.raises(RegraNegocioViolada, match="abaixo"):
        tenant_service.desativar(db_session, "pai-com-filho", ator)


def test_desativar_marca_inativo_desativa_usuarios_e_revoga_chave_api(db_session):
    ator = _ator(db_session)
    _tenant_alvo(db_session)
    usuario = Usuario(tenant_id=TENANT_ALVO, nome="Fulano", email="fulano@alvo.com", papel="admin", ativo=True)
    chave = ChaveApiParceiro(tenant_id=TENANT_ALVO, nome="Chave", prefixo="pk_abc", chave_hash="hash123")
    db_session.add_all([usuario, chave])
    db_session.commit()

    resultado = tenant_service.desativar(db_session, TENANT_ALVO, ator)

    assert resultado.ativo is False
    db_session.refresh(usuario)
    db_session.refresh(chave)
    assert usuario.ativo is False
    assert chave.revogada_em is not None


def test_desativar_recusa_se_ja_inativo(db_session):
    ator = _ator(db_session)
    _tenant_alvo(db_session)
    tenant_service.desativar(db_session, TENANT_ALVO, ator)

    with pytest.raises(RegraNegocioViolada, match="já está desativado"):
        tenant_service.desativar(db_session, TENANT_ALVO, ator)


def test_reativar_restringe_aos_usuarios_que_estavam_ativos_antes(db_session):
    """Não pode ressuscitar quem já estava inativo por outro motivo antes
    da desativação do tenant."""
    ator = _ator(db_session)
    _tenant_alvo(db_session)
    usuario_ativo = Usuario(tenant_id=TENANT_ALVO, nome="Ativo", email="ativo@alvo.com", papel="admin", ativo=True)
    usuario_ja_inativo = Usuario(
        tenant_id=TENANT_ALVO, nome="JaInativo", email="jainativo@alvo.com", papel="user", ativo=False
    )
    db_session.add_all([usuario_ativo, usuario_ja_inativo])
    db_session.commit()

    tenant_service.desativar(db_session, TENANT_ALVO, ator)
    tenant_service.reativar(db_session, TENANT_ALVO, ator)

    db_session.refresh(usuario_ativo)
    db_session.refresh(usuario_ja_inativo)
    assert usuario_ativo.ativo is True
    assert usuario_ja_inativo.ativo is False


def test_reativar_recusa_se_ja_ativo(db_session):
    ator = _ator(db_session)
    _tenant_alvo(db_session)

    with pytest.raises(RegraNegocioViolada, match="já está ativo"):
        tenant_service.reativar(db_session, TENANT_ALVO, ator)


def test_excluir_definitivamente_recusa_admin_no_proprio_tenant(db_session):
    _tenant_alvo(db_session)
    ator = _ator(db_session, papel="admin", tenant_id=TENANT_ALVO)

    with pytest.raises(NaoAutorizado):
        tenant_service.excluir_definitivamente(db_session, TENANT_ALVO, ator)


def test_excluir_definitivamente_recusa_com_filho(db_session):
    ator = _ator(db_session)
    _tenant_alvo(db_session, "pai-excluir")
    _tenant_alvo(db_session, "filho-excluir", tenant_pai_id="pai-excluir")

    with pytest.raises(RegraNegocioViolada, match="abaixo"):
        tenant_service.excluir_definitivamente(db_session, "pai-excluir", ator)


def _semear_tenant_alvo_completo(db_session) -> None:
    """Um pouco de tudo: dado operacional comum (deve sumir), dado com FK
    real pro tenant (usuario/licenca/chave_api — deve sumir), dado sem
    tenant_id próprio (campo_enriquecido — deve sumir via conta_id), e os
    dois casos que precisam sobreviver (pagamento_licenca por obrigação
    fiscal, registro_supressao_permanente por ser a própria garantia de
    "nunca mais recontatar")."""
    plano = Plano(nome="Plano Alvo", franquia_contas_mes=200, max_usuarios=10, preco_mensal=100.0)
    db_session.add(plano)
    db_session.flush()

    db_session.add(Licenca(tenant_id=TENANT_ALVO, plano_id=plano.id, status="ativa"))
    db_session.add(
        PagamentoLicenca(
            tenant_id=TENANT_ALVO, plano_id=plano.id, preferencia_id_externo="pref-1", status="aprovado", valor=100.0
        )
    )
    db_session.add(
        RegistroSupressaoPermanente(tenant_id=TENANT_ALVO, identificador_hash="hash-supressao-alvo")
    )
    db_session.add(Usuario(tenant_id=TENANT_ALVO, nome="Fulano", email="fulano@alvo-completo.com", papel="admin"))
    db_session.add(ChaveApiParceiro(tenant_id=TENANT_ALVO, nome="Chave", prefixo="pk_x", chave_hash="hash-x"))

    conta = Conta(tenant_id=TENANT_ALVO, icp_id=None, nome="Conta Alvo", status="prospectada")
    db_session.add(conta)
    db_session.flush()
    db_session.add(CampoEnriquecido(conta_id=conta.id, campo="dominio", valor="alvo.com.br", fonte="teste"))
    decisor = Decisor(tenant_id=TENANT_ALVO, conta_id=conta.id, nome="Decisor Alvo")
    db_session.add(decisor)
    db_session.flush()

    estagio = EstagioFunil(tenant_id=TENANT_ALVO, nome="Descoberta", ordem=1, tipo="aberto")
    db_session.add(estagio)
    db_session.flush()
    db_session.add(
        Negocio(
            tenant_id=TENANT_ALVO, conta_id=conta.id, estagio_id=estagio.id, nome="Negocio Alvo",
            valor=500.0, probabilidade=50, origem="manual",
        )
    )
    db_session.commit()


def test_excluir_definitivamente_apaga_dado_operacional_mas_mantem_retencao_legal(db_session):
    ator = _ator(db_session)
    _tenant_alvo(db_session)
    _semear_tenant_alvo_completo(db_session)

    tenant_service.excluir_definitivamente(db_session, TENANT_ALVO, ator)

    assert db_session.query(Tenant).filter_by(id=TENANT_ALVO).one_or_none() is None
    assert db_session.query(Usuario).filter_by(tenant_id=TENANT_ALVO).count() == 0
    assert db_session.query(Licenca).filter_by(tenant_id=TENANT_ALVO).count() == 0
    assert db_session.query(Conta).filter_by(tenant_id=TENANT_ALVO).count() == 0
    assert db_session.query(Decisor).filter_by(tenant_id=TENANT_ALVO).count() == 0
    assert db_session.query(Negocio).filter_by(tenant_id=TENANT_ALVO).count() == 0
    assert db_session.query(ChaveApiParceiro).filter_by(tenant_id=TENANT_ALVO).count() == 0
    assert db_session.query(CampoEnriquecido).count() == 0  # a única linha era da conta apagada

    # Retenção legal — sobrevivem de propósito.
    assert db_session.query(PagamentoLicenca).filter_by(tenant_id=TENANT_ALVO).count() == 1
    assert db_session.query(RegistroSupressaoPermanente).filter_by(tenant_id=TENANT_ALVO).count() == 1

    # Log de sobrevivência sob o tenant de quem executou, não o alvo.
    log = (
        db_session.query(AuditLog)
        .filter_by(tenant_id=TENANT_ATUANTE, evento_tipo="tenant_excluido_definitivamente")
        .one_or_none()
    )
    assert log is not None
    assert log.detalhes["tenant_id"] == TENANT_ALVO


def test_excluir_definitivamente_completude_via_varredura_do_schema(db_session):
    """Prova direta de que a varredura dinâmica não deixa nada pra trás:
    reaplica a mesma técnica de `Base.metadata.sorted_tables` depois da
    exclusão e garante zero linhas pro tenant alvo em qualquer tabela fora
    da exclude-list de retenção legal."""
    ator = _ator(db_session)
    _tenant_alvo(db_session)
    _semear_tenant_alvo_completo(db_session)

    tenant_service.excluir_definitivamente(db_session, TENANT_ALVO, ator)

    retencao_legal = {"pagamento_licenca", "registro_supressao_permanente"}
    for table in Base.metadata.sorted_tables:
        if table.name in retencao_legal or table.name == "tenant":
            continue
        colunas_tenant = [coluna for coluna in table.columns if coluna.name.startswith("tenant_id")]
        if not colunas_tenant:
            continue
        condicao = None
        for coluna in colunas_tenant:
            clausula = coluna == TENANT_ALVO
            condicao = clausula if condicao is None else (condicao | clausula)
        total = db_session.execute(select(func.count()).select_from(table).where(condicao)).scalar_one()
        assert total == 0, f"tabela {table.name} ainda tem linha(s) do tenant excluído"


def test_excluir_definitivamente_retoma_de_uma_varredura_parcial(db_session):
    """Simula o que sobraria se um request anterior tivesse caído no meio
    (algumas tabelas já vazias pra esse tenant, outras ainda cheias) —
    rodar de novo precisa completar sem erro, não travar achando que já
    devia estar tudo limpo."""
    ator = _ator(db_session)
    _tenant_alvo(db_session)
    _semear_tenant_alvo_completo(db_session)

    # Simula uma rodada anterior que já tinha limpado só os filhos mais
    # profundos (mesmas tabelas que a varredura real chegaria primeiro).
    db_session.query(CampoEnriquecido).delete()
    db_session.query(Negocio).filter_by(tenant_id=TENANT_ALVO).delete()
    db_session.commit()

    tenant_service.excluir_definitivamente(db_session, TENANT_ALVO, ator)

    assert db_session.query(Tenant).filter_by(id=TENANT_ALVO).one_or_none() is None
    assert db_session.query(Usuario).filter_by(tenant_id=TENANT_ALVO).count() == 0

    from app.services.errors import NaoEncontrado

    with pytest.raises(NaoEncontrado):
        tenant_service.excluir_definitivamente(db_session, TENANT_ALVO, ator)
