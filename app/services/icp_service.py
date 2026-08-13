import uuid

from sqlalchemy.orm import Session

from app.models.conta import Conta
from app.models.icp import ICP
from app.models.oferta import Oferta
from app.schemas.icp import ICPCreateSchema
from app.services import auditoria_service
from app.services.errors import NaoEncontrado


def existe_icp_ativo(db: Session, tenant_id: str) -> bool:
    return db.query(ICP).filter_by(tenant_id=tenant_id, ativo=True).first() is not None


def obter(db: Session, tenant_id: str, icp_id: int) -> ICP:
    icp = db.query(ICP).filter_by(id=icp_id, tenant_id=tenant_id).one_or_none()
    if icp is None:
        raise NaoEncontrado(f"ICP {icp_id} não encontrado")
    return icp


def listar(db: Session, tenant_id: str, apenas_ativos: bool = False) -> list[ICP]:
    query = db.query(ICP).filter_by(tenant_id=tenant_id)
    if apenas_ativos:
        query = query.filter_by(ativo=True)
    return query.order_by(ICP.grupo_id, ICP.versao).all()


def historico(db: Session, tenant_id: str, grupo_id: str) -> list[ICP]:
    return (
        db.query(ICP)
        .filter_by(tenant_id=tenant_id, grupo_id=grupo_id)
        .order_by(ICP.versao)
        .all()
    )


def criar(db: Session, tenant_id: str, ator_id: str | None, dados: ICPCreateSchema) -> ICP:
    icp = ICP(
        tenant_id=tenant_id,
        grupo_id=str(uuid.uuid4()),
        nome=dados.nome,
        versao=1,
        ativo=True,
        segmento=dados.segmento,
        porte=dados.porte,
        regiao=dados.regiao,
        dores=dados.dores,
        gatilhos=dados.gatilhos,
        cnae_codigos=dados.cnae_codigos,
        ufs=dados.ufs,
    )
    db.add(icp)
    db.flush()

    auditoria_service.registrar(db, tenant_id, "icp_criado", "icp", icp.id, ator_id, {"nome": icp.nome})
    db.commit()
    db.refresh(icp)
    return icp


def nova_versao(db: Session, tenant_id: str, ator_id: str | None, icp_id: int, dados: ICPCreateSchema) -> ICP:
    """ICP versionado e editável a qualquer momento (E1-H1) — a edição nunca
    sobrescreve a versão anterior, preservando o histórico."""
    atual = obter(db, tenant_id, icp_id)

    versao_maxima = max(v.versao for v in historico(db, tenant_id, atual.grupo_id))

    nova = ICP(
        tenant_id=tenant_id,
        grupo_id=atual.grupo_id,
        nome=dados.nome,
        versao=versao_maxima + 1,
        ativo=True,
        segmento=dados.segmento,
        porte=dados.porte,
        regiao=dados.regiao,
        dores=dados.dores,
        gatilhos=dados.gatilhos,
        cnae_codigos=dados.cnae_codigos,
        ufs=dados.ufs,
    )

    db.query(ICP).filter_by(tenant_id=tenant_id, grupo_id=atual.grupo_id).update({"ativo": False})
    db.add(nova)
    db.flush()

    auditoria_service.registrar(
        db, tenant_id, "icp_nova_versao", "icp", nova.id, ator_id, {"grupo_id": nova.grupo_id, "versao": nova.versao}
    )
    db.commit()
    db.refresh(nova)
    return nova


def clonar(db: Session, tenant_id: str, ator_id: str | None, icp_id: int) -> ICP:
    """Clonagem em 1 clique: nova linhagem independente, preservando o
    ICP original intacto (E1-H4)."""
    origem = obter(db, tenant_id, icp_id)

    clone = ICP(
        tenant_id=tenant_id,
        grupo_id=str(uuid.uuid4()),
        clonado_de_id=origem.id,
        nome=f"{origem.nome} (cópia)",
        versao=1,
        ativo=True,
        segmento=origem.segmento,
        porte=origem.porte,
        regiao=origem.regiao,
        dores=list(origem.dores),
        gatilhos=list(origem.gatilhos),
        cnae_codigos=list(origem.cnae_codigos),
        ufs=list(origem.ufs),
    )
    db.add(clone)
    db.flush()

    auditoria_service.registrar(db, tenant_id, "icp_clonado", "icp", clone.id, ator_id, {"origem_id": origem.id})
    db.commit()
    db.refresh(clone)
    return clone


def excluir(db: Session, tenant_id: str, ator_id: str | None, icp_id: int) -> None:
    """Remove um ICP cadastrado errado/não mais usado, sem arrastar contas
    ou ofertas reais junto — elas ficam sem ICP (mesmo tratamento de leads
    avulsos, já suportado em toda a tela de Prospecção), em vez de serem
    apagadas ou de bloquear a exclusão. ICPs clonados a partir deste
    perdem a referência (`clonado_de_id`), mas continuam intactos."""
    icp = obter(db, tenant_id, icp_id)

    db.query(Conta).filter_by(tenant_id=tenant_id, icp_id=icp.id).update({"icp_id": None})
    db.query(Oferta).filter_by(tenant_id=tenant_id, icp_id=icp.id).update({"icp_id": None})
    db.query(ICP).filter_by(tenant_id=tenant_id, clonado_de_id=icp.id).update({"clonado_de_id": None})

    auditoria_service.registrar(db, tenant_id, "icp_excluido", "icp", icp.id, ator_id, {"nome": icp.nome})
    db.delete(icp)
    db.commit()


def performance(db: Session, tenant_id: str) -> list[dict]:
    """Comparativo simples entre ICPs ativos (E1-H4)."""
    resultado = []
    for icp in listar(db, tenant_id, apenas_ativos=True):
        contas = db.query(Conta).filter_by(tenant_id=tenant_id, icp_id=icp.id).all()
        scores = [conta.score_aderencia for conta in contas if conta.score_aderencia is not None]

        por_status: dict[str, int] = {}
        for conta in contas:
            por_status[conta.status] = por_status.get(conta.status, 0) + 1

        resultado.append(
            {
                "icp_id": icp.id,
                "nome": icp.nome,
                "versao": icp.versao,
                "total_contas": len(contas),
                "score_medio": (sum(scores) / len(scores)) if scores else None,
                "contas_por_status": por_status,
            }
        )
    return resultado
