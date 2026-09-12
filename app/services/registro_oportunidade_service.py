import re
from datetime import UTC, datetime, timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.conta import Conta
from app.models.registro_oportunidade import RegistroOportunidade
from app.models.solicitacao_desconto import SolicitacaoDesconto
from app.models.usuario import Usuario
from app.providers.plan_limits.base import PlanLimitsProvider
from app.services import auditoria_service, tenant_service
from app.services.errors import NaoEncontrado, RegraNegocioViolada, ValidacaoFalhou

_DIAS_VALIDADE_REGISTRO = 90
_STATUS_ATIVOS_ENCERRAVEIS = {"ganho", "perdido", "cancelado"}


def _normalizar_cnpj(cnpj: str) -> str:
    digitos = re.sub(r"\D", "", cnpj or "")
    if len(digitos) != 14:
        raise ValidacaoFalhou("CNPJ inválido — informe os 14 dígitos.")
    return digitos


def registrar_oportunidade(
    db: Session,
    usuario: Usuario,
    ator_id: str | None,
    plan_limits: PlanLimitsProvider,
    cnpj: str,
    nome_empresa: str,
    conta_id: int | None = None,
) -> RegistroOportunidade:
    """Deal registration: garante que `usuario.tenant_id` fica PRIME do
    CNPJ dentro da própria rede (`tenant_service.tenant_ids_da_rede`). O
    conflito é resolvido pelo índice único parcial em
    `registro_oportunidade` (rede + cnpj, só entre os `status="ativo"`),
    não por um SELECT prévio — evita a corrida entre dois revendedores
    registrando a mesma empresa ao mesmo tempo."""
    if usuario.papel != "super_admin" and not plan_limits.permite_registro_oportunidade(usuario.tenant_id):
        raise RegraNegocioViolada("Registro de Oportunidade é exclusivo do plano Professional ou superior.")

    cnpj_normalizado = _normalizar_cnpj(cnpj)
    rede_raiz_tenant_id = tenant_service.obter_raiz_da_rede(db, usuario.tenant_id)

    if conta_id is not None:
        tenant_ids_rede = tenant_service.tenant_ids_da_rede(db, usuario.tenant_id)
        conta = db.query(Conta).filter_by(id=conta_id).one_or_none()
        if conta is None or conta.tenant_id not in tenant_ids_rede:
            raise NaoEncontrado(f"Conta {conta_id} não encontrada")

    registro = RegistroOportunidade(
        tenant_id=usuario.tenant_id,
        rede_raiz_tenant_id=rede_raiz_tenant_id,
        vendedor_usuario_id=usuario.id,
        cnpj=cnpj_normalizado,
        nome_empresa=nome_empresa,
        conta_id=conta_id,
        status="ativo",
        expira_em=datetime.now(UTC) + timedelta(days=_DIAS_VALIDADE_REGISTRO),
    )
    db.add(registro)
    try:
        db.flush()
    except IntegrityError as erro:
        db.rollback()
        raise RegraNegocioViolada(
            "Já existe um Registro de Oportunidade ativo para este CNPJ nesta rede."
        ) from erro

    auditoria_service.registrar(
        db, usuario.tenant_id, "registro_oportunidade_criado", "registro_oportunidade", registro.id, ator_id,
        {"cnpj": cnpj_normalizado, "nome_empresa": nome_empresa},
    )
    db.commit()
    db.refresh(registro)
    return registro


def vincular_conta_criada(db: Session, conta: Conta) -> None:
    """Chamado depois de uma `Conta` ser criada (`conta_service.criar_lead`/
    `criar_manual`/`gerar_lista`): se o CNPJ dela já tiver um RO ativo
    sem `conta_id` na mesma rede, linka os dois. No-op se a conta não
    tem CNPJ ou se já existe/não há RO correspondente — nunca levanta
    erro, é só um "melhor esforço" de sincronização."""
    if not conta.cnpj:
        return
    try:
        cnpj_normalizado = _normalizar_cnpj(conta.cnpj)
    except ValidacaoFalhou:
        return

    rede_raiz_tenant_id = tenant_service.obter_raiz_da_rede(db, conta.tenant_id)
    registro = (
        db.query(RegistroOportunidade)
        .filter_by(
            rede_raiz_tenant_id=rede_raiz_tenant_id, cnpj=cnpj_normalizado, status="ativo", conta_id=None,
        )
        .one_or_none()
    )
    if registro is None:
        return
    registro.conta_id = conta.id
    db.commit()


def _obter_registro(db: Session, registro_id: int) -> RegistroOportunidade:
    registro = db.query(RegistroOportunidade).filter_by(id=registro_id).one_or_none()
    if registro is None:
        raise NaoEncontrado(f"Registro de Oportunidade {registro_id} não encontrado")
    return registro


def listar_registros(
    db: Session, usuario: Usuario, tenant_id_selecionado: str | None = None
) -> list[RegistroOportunidade]:
    tenant_ids = tenant_service.tenant_ids_no_escopo(db, usuario, tenant_id_selecionado)
    return (
        db.query(RegistroOportunidade)
        .filter(RegistroOportunidade.tenant_id.in_(tenant_ids))
        .order_by(RegistroOportunidade.criado_em.desc())
        .all()
    )


def atualizar_status(
    db: Session, usuario: Usuario, ator_id: str | None, registro_id: int, novo_status: str
) -> RegistroOportunidade:
    if novo_status not in _STATUS_ATIVOS_ENCERRAVEIS:
        raise ValidacaoFalhou(f"Status inválido: {novo_status}")
    registro = _obter_registro(db, registro_id)
    tenant_ids_no_escopo = tenant_service.tenant_ids_no_escopo(db, usuario, None)
    if registro.tenant_id not in tenant_ids_no_escopo:
        raise NaoEncontrado(f"Registro de Oportunidade {registro_id} não encontrado")

    registro.status = novo_status
    auditoria_service.registrar(
        db, registro.tenant_id, "registro_oportunidade_status_atualizado", "registro_oportunidade", registro.id,
        ator_id, {"novo_status": novo_status},
    )
    db.commit()
    db.refresh(registro)
    return registro


def expirar_registros_vencidos(db: Session) -> int:
    """Cron (`POST /cron/expirar-registros-oportunidade`): libera o CNPJ
    pra um novo registro quando o antigo passa da validade sem decisão."""
    agora = datetime.now(UTC)
    registros = db.query(RegistroOportunidade).filter(
        RegistroOportunidade.status == "ativo", RegistroOportunidade.expira_em < agora
    ).all()
    for registro in registros:
        registro.status = "expirado"
    db.commit()
    return len(registros)


def solicitar_desconto(
    db: Session, usuario: Usuario, ator_id: str | None, registro_id: int, percentual_solicitado: float,
    justificativa: str | None = None,
) -> SolicitacaoDesconto:
    registro = _obter_registro(db, registro_id)
    if registro.tenant_id != usuario.tenant_id or registro.status != "ativo":
        raise RegraNegocioViolada("Você não é PRIME desta oportunidade — outro tenant já detém o registro ativo.")

    solicitacao = SolicitacaoDesconto(
        tenant_id=usuario.tenant_id,
        registro_oportunidade_id=registro.id,
        solicitante_usuario_id=usuario.id,
        percentual_solicitado=percentual_solicitado,
        justificativa=justificativa,
        status="pendente",
    )
    db.add(solicitacao)
    db.flush()
    auditoria_service.registrar(
        db, usuario.tenant_id, "solicitacao_desconto_criada", "solicitacao_desconto", solicitacao.id, ator_id,
        {"registro_oportunidade_id": registro.id, "percentual_solicitado": percentual_solicitado},
    )
    db.commit()
    db.refresh(solicitacao)
    return solicitacao


def listar_solicitacoes_desconto(db: Session, usuario: Usuario) -> list[SolicitacaoDesconto]:
    """Quem não é admin/super_admin do tenant raiz da rede só vê os
    próprios pedidos; quem é (o "fabricante") vê todos os pendentes da
    rede — mesma regra de `decidir_solicitacao_desconto` abaixo."""
    query = db.query(SolicitacaoDesconto).join(
        RegistroOportunidade, SolicitacaoDesconto.registro_oportunidade_id == RegistroOportunidade.id
    )
    if usuario.papel == "super_admin":
        return query.order_by(SolicitacaoDesconto.criado_em.desc()).all()

    rede_raiz_tenant_id = tenant_service.obter_raiz_da_rede(db, usuario.tenant_id)
    if usuario.papel == "admin" and usuario.tenant_id == rede_raiz_tenant_id:
        return (
            query.filter(RegistroOportunidade.rede_raiz_tenant_id == rede_raiz_tenant_id)
            .order_by(SolicitacaoDesconto.criado_em.desc())
            .all()
        )
    return (
        query.filter(SolicitacaoDesconto.tenant_id == usuario.tenant_id)
        .order_by(SolicitacaoDesconto.criado_em.desc())
        .all()
    )


def decidir_solicitacao_desconto(
    db: Session, usuario: Usuario, ator_id: str | None, solicitacao_id: int, aprovar: bool,
    motivo: str | None = None,
) -> SolicitacaoDesconto:
    """Só o admin do tenant RAIZ da rede (o "fabricante") decide — não
    qualquer admin da subárvore, já que é ele quem concede a
    vantagem/desconto pra toda a rede. `super_admin` sempre pode."""
    solicitacao = db.query(SolicitacaoDesconto).filter_by(id=solicitacao_id).one_or_none()
    if solicitacao is None:
        raise NaoEncontrado(f"Solicitação de desconto {solicitacao_id} não encontrada")
    registro = _obter_registro(db, solicitacao.registro_oportunidade_id)

    if usuario.papel != "super_admin" and usuario.tenant_id != registro.rede_raiz_tenant_id:
        raise NaoEncontrado(f"Solicitação de desconto {solicitacao_id} não encontrada")

    solicitacao.status = "aprovado" if aprovar else "rejeitado"
    solicitacao.aprovador_usuario_id = usuario.id
    solicitacao.motivo_decisao = motivo
    solicitacao.decidido_em = datetime.now(UTC)
    auditoria_service.registrar(
        db, registro.rede_raiz_tenant_id, "solicitacao_desconto_decidida", "solicitacao_desconto", solicitacao.id,
        ator_id, {"aprovado": aprovar, "motivo": motivo},
    )
    db.commit()
    db.refresh(solicitacao)
    return solicitacao
