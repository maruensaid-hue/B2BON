from datetime import date

from sqlalchemy.orm import Session

from app.contexts.network.contract import grafo, identidade, privacidade
from app.models.empresa_rede import EmpresaRede
from app.models.perfil_empresa import PerfilEmpresa
from app.models.relacionamento_empresarial import RelacionamentoEmpresarial
from app.services import auditoria_service
from app.services.errors import NaoAutorizado, NaoEncontrado, ValidacaoFalhou

TIPOS_VALIDOS = grafo.TIPOS_DECLARAVEIS
VISIBILIDADES_VALIDAS = set(privacidade.VISIBILIDADES)


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
    outro_perfil = (
        db.query(PerfilEmpresa).filter_by(tenant_id=outro_tenant_id).one_or_none() if outro_tenant_id else None
    )
    outra_empresa_id = (
        relacionamento.empresa_destino_id
        if relacionamento.tenant_id_origem == tenant_id_ponto_de_vista
        else relacionamento.empresa_origem_id
    )
    outra_empresa = db.get(EmpresaRede, outra_empresa_id) if outra_empresa_id else None
    if outro_perfil is not None:
        outro_nome = outro_perfil.nome_exibicao
    elif outra_empresa is not None:
        outro_nome = outra_empresa.nome_exibicao
    else:
        outro_nome = outro_tenant_id
    return {
        "id": relacionamento.id,
        "tenant_id_origem": relacionamento.tenant_id_origem,
        "tenant_id_destino": relacionamento.tenant_id_destino,
        "outro_tenant_nome": outro_nome,
        "empresa_origem_id": relacionamento.empresa_origem_id,
        "empresa_destino_id": relacionamento.empresa_destino_id,
        "destino_reivindicado": relacionamento.tenant_id_destino is not None,
        "fonte": relacionamento.fonte,
        "valido_desde": relacionamento.valido_desde,
        "valido_ate": relacionamento.valido_ate,
        "tipo": relacionamento.tipo,
        "visibilidade": relacionamento.visibilidade,
        "confianca": relacionamento.confianca,
        "pode_confirmar": (
            relacionamento.tenant_id_destino == tenant_id_consultante and relacionamento.confianca == "autodeclarada"
        ),
        "criado_em": relacionamento.criado_em,
    }


def _validar(tipo: str, visibilidade: str, valido_desde: date | None, valido_ate: date | None) -> None:
    if tipo not in TIPOS_VALIDOS:
        raise ValidacaoFalhou(f"Tipo de relacionamento inválido: {tipo}")
    if visibilidade not in VISIBILIDADES_VALIDAS:
        raise ValidacaoFalhou(f"Visibilidade inválida: {visibilidade}")
    if valido_desde and valido_ate and valido_ate < valido_desde:
        raise ValidacaoFalhou("A validade final é anterior à inicial.")


def declarar(
    db: Session,
    tenant_id_origem: str,
    ator_id: str | None,
    tenant_id_destino: str,
    tipo: str,
    visibilidade: str,
    valido_desde: date | None = None,
    valido_ate: date | None = None,
) -> dict:
    if tenant_id_origem == tenant_id_destino:
        raise ValidacaoFalhou("Não é possível declarar um relacionamento com o próprio tenant.")
    _validar(tipo, visibilidade, valido_desde, valido_ate)
    return _criar(
        db, tenant_id_origem, ator_id, identidade.garantir_do_tenant(db, tenant_id_destino),
        tipo, visibilidade, valido_desde, valido_ate,
    )


def declarar_por_cnpj(
    db: Session,
    tenant_id_origem: str,
    ator_id: str | None,
    cnpj: str,
    nome: str | None,
    tipo: str,
    visibilidade: str,
    valido_desde: date | None = None,
    valido_ate: date | None = None,
) -> dict:
    """Relacionamento com uma empresa que pode ainda não estar na rede
    (Company Claim, Fase 7): se o CNPJ já tem dono, aponta para ele."""
    _validar(tipo, visibilidade, valido_desde, valido_ate)
    destino = identidade.por_cnpj(db, cnpj, nome, tenant_id_origem)
    if destino.tenant_id == tenant_id_origem:
        raise ValidacaoFalhou("Não é possível declarar um relacionamento com o próprio tenant.")
    return _criar(db, tenant_id_origem, ator_id, destino, tipo, visibilidade, valido_desde, valido_ate)


def _criar(db, tenant_id_origem, ator_id, destino, tipo, visibilidade, valido_desde, valido_ate) -> dict:
    tenant_id_destino = destino.tenant_id
    relacionamento = RelacionamentoEmpresarial(
        tenant_id_origem=tenant_id_origem,
        tenant_id_destino=tenant_id_destino,
        empresa_origem_id=identidade.garantir_do_tenant(db, tenant_id_origem).id,
        empresa_destino_id=destino.id,
        tipo=tipo,
        visibilidade=visibilidade,
        confianca="autodeclarada",
        fonte="DECLARADA",
        valido_desde=valido_desde,
        valido_ate=valido_ate,
        criado_por=ator_id,
    )
    db.add(relacionamento)
    db.flush()

    auditoria_service.registrar(
        db, tenant_id_origem, "relacionamento_empresarial_declarado", "relacionamento_empresarial",
        relacionamento.id, ator_id, {"tenant_id_destino": tenant_id_destino, "empresa_destino_id": destino.id, "tipo": tipo},
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
    relacionamento.fonte = "CONFIRMADA"

    auditoria_service.registrar(
        db, tenant_id, "relacionamento_empresarial_confirmado", "relacionamento_empresarial",
        relacionamento.id, ator_id, {},
    )
    db.commit()
    db.refresh(relacionamento)
    return _serializar(db, tenant_id, tenant_id, relacionamento)


def listar_da_empresa(db: Session, tenant_id: str, tenant_id_alvo: str) -> list[dict]:
    """Relacionamentos onde `tenant_id_alvo` é origem OU destino, filtrados
    pela regra única de privacidade da rede (Fase 7): `publica` para todos
    (menos bloqueados), `conexoes` para as partes e conexões do autor,
    `privada` só para quem declarou — nem a empresa citada vê."""
    query = db.query(RelacionamentoEmpresarial).filter(
        (RelacionamentoEmpresarial.tenant_id_origem == tenant_id_alvo)
        | (RelacionamentoEmpresarial.tenant_id_destino == tenant_id_alvo)
    )
    cache: dict = {}
    relacionamentos = [
        r for r in query.order_by(RelacionamentoEmpresarial.criado_em.desc()).all()
        if grafo.aresta_visivel(db, tenant_id, r, cache)
    ]
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
