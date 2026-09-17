from sqlalchemy.orm import Session

from app.models.perfil_empresa import PerfilEmpresa
from app.models.relacionamento_empresarial import RelacionamentoEmpresarial
from app.services import auditoria_service
from app.services.errors import NaoAutorizado, NaoEncontrado, ValidacaoFalhou

TIPOS_VALIDOS = {
    "SUPPLIER_OF", "CUSTOMER_OF", "PARTNER_OF", "RESELLER_OF", "DISTRIBUTOR_OF",
    "INTEGRATES_WITH", "USES_TECHNOLOGY", "PROVIDES_SERVICE", "PROVIDES_PRODUCT",
    "INVESTS_IN", "INTERESTED_IN", "LOOKING_FOR",
}
VISIBILIDADES_VALIDAS = {"publica", "conexoes", "privada"}


def _serializar(
    db: Session, tenant_id_consultante: str, tenant_id_ponto_de_vista: str, relacionamento: RelacionamentoEmpresarial
) -> dict:
    """`tenant_id_ponto_de_vista` é de qual lado olhar pra achar "a outra
    empresa" (o alvo da listagem, não necessariamente quem está
    consultando — dá pra ver os relacionamentos públicos de terceiros).
    `tenant_id_consultante` só importa pra `pode_confirmar` (só a
    contraparte de verdade pode confirmar, nunca um terceiro olhando)."""
    outro_tenant_id = (
        relacionamento.tenant_id_destino
        if relacionamento.tenant_id_origem == tenant_id_ponto_de_vista
        else relacionamento.tenant_id_origem
    )
    outro_perfil = db.query(PerfilEmpresa).filter_by(tenant_id=outro_tenant_id).one_or_none()
    return {
        "id": relacionamento.id,
        "tenant_id_origem": relacionamento.tenant_id_origem,
        "tenant_id_destino": relacionamento.tenant_id_destino,
        "outro_tenant_nome": outro_perfil.nome_exibicao if outro_perfil is not None else outro_tenant_id,
        "tipo": relacionamento.tipo,
        "visibilidade": relacionamento.visibilidade,
        "confianca": relacionamento.confianca,
        "pode_confirmar": (
            relacionamento.tenant_id_destino == tenant_id_consultante and relacionamento.confianca == "autodeclarada"
        ),
        "criado_em": relacionamento.criado_em,
    }


def declarar(
    db: Session, tenant_id_origem: str, ator_id: str | None, tenant_id_destino: str, tipo: str, visibilidade: str
) -> dict:
    if tenant_id_origem == tenant_id_destino:
        raise ValidacaoFalhou("Não é possível declarar um relacionamento com o próprio tenant.")
    if tipo not in TIPOS_VALIDOS:
        raise ValidacaoFalhou(f"Tipo de relacionamento inválido: {tipo}")
    if visibilidade not in VISIBILIDADES_VALIDAS:
        raise ValidacaoFalhou(f"Visibilidade inválida: {visibilidade}")

    relacionamento = RelacionamentoEmpresarial(
        tenant_id_origem=tenant_id_origem,
        tenant_id_destino=tenant_id_destino,
        tipo=tipo,
        visibilidade=visibilidade,
        confianca="autodeclarada",
        criado_por=ator_id,
    )
    db.add(relacionamento)
    db.flush()

    auditoria_service.registrar(
        db, tenant_id_origem, "relacionamento_empresarial_declarado", "relacionamento_empresarial",
        relacionamento.id, ator_id, {"tenant_id_destino": tenant_id_destino, "tipo": tipo},
    )
    db.commit()
    db.refresh(relacionamento)
    return _serializar(db, tenant_id_origem, tenant_id_origem, relacionamento)


def confirmar(db: Session, tenant_id: str, ator_id: str | None, relacionamento_id: int) -> dict:
    """Só a contraparte (`tenant_id_destino`) pode confirmar — mesmo
    espírito do aceite de `ConexaoEmpresa`, sobe `confianca` de
    autodeclarada pra confirmada, sem exigir uma conexão social aceita."""
    relacionamento = db.query(RelacionamentoEmpresarial).filter_by(id=relacionamento_id).one_or_none()
    if relacionamento is None:
        raise NaoEncontrado(f"Relacionamento {relacionamento_id} não encontrado")
    if relacionamento.tenant_id_destino != tenant_id:
        raise NaoAutorizado("Só a empresa destino pode confirmar este relacionamento.")

    relacionamento.confianca = "confirmada_pela_contraparte"

    auditoria_service.registrar(
        db, tenant_id, "relacionamento_empresarial_confirmado", "relacionamento_empresarial",
        relacionamento.id, ator_id, {},
    )
    db.commit()
    db.refresh(relacionamento)
    return _serializar(db, tenant_id, tenant_id, relacionamento)


def listar_da_empresa(db: Session, tenant_id: str, tenant_id_alvo: str) -> list[dict]:
    """Relacionamentos onde `tenant_id_alvo` é origem OU destino,
    filtrados por visibilidade do ponto de vista de quem consulta
    (`tenant_id`): sempre vê os próprios; de terceiros, só `publica`
    (`conexoes`/`privada` ficam de fora até a Fase 2 saber calcular
    "somos conectados" aqui — YAGNI por agora, evita over-promise)."""
    query = db.query(RelacionamentoEmpresarial).filter(
        (RelacionamentoEmpresarial.tenant_id_origem == tenant_id_alvo)
        | (RelacionamentoEmpresarial.tenant_id_destino == tenant_id_alvo)
    )
    if tenant_id_alvo != tenant_id:
        query = query.filter(RelacionamentoEmpresarial.visibilidade == "publica")
    relacionamentos = query.order_by(RelacionamentoEmpresarial.criado_em.desc()).all()
    return [_serializar(db, tenant_id, tenant_id_alvo, relacionamento) for relacionamento in relacionamentos]


def remover(db: Session, tenant_id: str, ator_id: str | None, relacionamento_id: int) -> None:
    relacionamento = db.query(RelacionamentoEmpresarial).filter_by(id=relacionamento_id).one_or_none()
    if relacionamento is None or relacionamento.tenant_id_origem != tenant_id:
        raise NaoEncontrado(f"Relacionamento {relacionamento_id} não encontrado")

    auditoria_service.registrar(
        db, tenant_id, "relacionamento_empresarial_removido", "relacionamento_empresarial",
        relacionamento.id, ator_id, {"tipo": relacionamento.tipo},
    )
    db.delete(relacionamento)
    db.commit()
