"""Business Graph (Fase 7, §28-§29) sobre tabelas relacionais (D-024).

Arestas declaradas (`relacionamento_empresarial`) + CONNECTED_TO derivada
das conexões aceitas (não duplicada em tabela). Toda leitura passa por
`privacidade.pode_ver`. Grafos lógicos: COMPANY e RELATIONSHIP aqui;
PEOPLE (decisores) continua privado do tenant; OPPORTUNITY e PROCUREMENT
chegam nas Fases 8-10 sobre a mesma forma de aresta.
"""

from datetime import date

from sqlalchemy.orm import Session

from app.contexts.network import identidade, privacidade
from app.contexts.shared.canonical.base import DataOrigin
from app.contexts.shared.canonical.network import (
    BusinessEdge,
    BusinessRelationType,
    CompanyIdentity,
    CompanyStatus,
    EdgeConfidence,
    EdgeVerification,
    EdgeVisibility,
)
from app.models.conexao_empresa import ConexaoEmpresa
from app.models.empresa_rede import EmpresaRede
from app.models.relacionamento_empresarial import RelacionamentoEmpresarial

TIPOS_DECLARAVEIS = frozenset(t.value for t in BusinessRelationType if t is not BusinessRelationType.CONNECTED_TO)
_ORIGEM = {"TENANT": DataOrigin.SELF_DECLARED, "DECLARADA_POR_TERCEIRO": DataOrigin.SELF_DECLARED, "OFICIAL": DataOrigin.OFFICIAL}


def identidade_canonica(empresa: EmpresaRede) -> CompanyIdentity:
    return CompanyIdentity(
        id=empresa.id, tenant_id=empresa.tenant_id, cnpj=empresa.cnpj, display_name=empresa.nome_exibicao,
        status=CompanyStatus(empresa.status), origin=_ORIGEM.get(empresa.origem, DataOrigin.SELF_DECLARED),
    )


def confianca(aresta: RelacionamentoEmpresarial, hoje: date | None = None) -> EdgeConfidence:
    """Categórica e explicável: confirmada pela contraparte = ALTA;
    autodeclarada = MEDIA; fora da validade declarada = BAIXA."""
    hoje = hoje or date.today()
    if aresta.valido_ate is not None and aresta.valido_ate < hoje:
        return EdgeConfidence.LOW
    return EdgeConfidence.HIGH if aresta.confianca == "confirmada_pela_contraparte" else EdgeConfidence.MEDIUM


def _empresa(db: Session, empresa_id: int | None, tenant_id: str | None) -> EmpresaRede | None:
    if empresa_id is not None:
        return db.get(EmpresaRede, empresa_id)
    return identidade.garantir_do_tenant(db, tenant_id) if tenant_id else None


def aresta_canonica(db: Session, aresta: RelacionamentoEmpresarial) -> BusinessEdge:
    origem = _empresa(db, aresta.empresa_origem_id, aresta.tenant_id_origem)
    destino = _empresa(db, aresta.empresa_destino_id, aresta.tenant_id_destino)
    return BusinessEdge(
        id=f"rel:{aresta.id}",
        type=BusinessRelationType(aresta.tipo),
        from_company=identidade_canonica(origem),
        to_company=identidade_canonica(destino),
        source=aresta.fonte or "DECLARADA",
        visibility=EdgeVisibility(aresta.visibilidade),
        confidence=confianca(aresta),
        verification=EdgeVerification(aresta.confianca),
        valid_from=aresta.valido_desde,
        valid_until=aresta.valido_ate,
        creator_tenant_id=aresta.tenant_id_origem,
        metadata=aresta.metadados or {},
    )


def aresta_visivel(db: Session, consultante: str, aresta: RelacionamentoEmpresarial, cache: dict | None = None) -> bool:
    return privacidade.pode_ver(
        db, consultante, aresta.tenant_id_origem, aresta.visibilidade, partes=(aresta.tenant_id_destino,), cache=cache
    )


def arestas_da_empresa(db: Session, consultante: str, empresa_id: int) -> list[BusinessEdge]:
    """Vizinhança de uma empresa como o `consultante` pode vê-la."""
    empresa = db.get(EmpresaRede, empresa_id)
    if empresa is None or empresa.status == "MESCLADA":
        return []
    consulta = db.query(RelacionamentoEmpresarial).filter(
        (RelacionamentoEmpresarial.empresa_origem_id == empresa.id)
        | (RelacionamentoEmpresarial.empresa_destino_id == empresa.id)
    )
    cache: dict = {}
    arestas = [aresta_canonica(db, a) for a in consulta.all() if aresta_visivel(db, consultante, a, cache)]

    if empresa.tenant_id is not None and consultante == empresa.tenant_id:
        # CONNECTED_TO só para as próprias conexões (conexão não é pública).
        propria = identidade_canonica(empresa)
        for outro in sorted(privacidade.conectados(db, consultante)):
            outra = identidade_canonica(identidade.garantir_do_tenant(db, outro))
            arestas.append(BusinessEdge(
                id=f"conexao:{min(consultante, outro)}:{max(consultante, outro)}",
                type=BusinessRelationType.CONNECTED_TO, from_company=propria, to_company=outra,
                source="CONEXAO", visibility=EdgeVisibility.CONNECTIONS, confidence=EdgeConfidence.HIGH,
                verification=EdgeVerification.PLATFORM_CONNECTION, creator_tenant_id=None,
            ))
    return arestas


def conexao_aceita(db: Session, a: str, b: str) -> bool:
    return (
        db.query(ConexaoEmpresa)
        .filter(
            ConexaoEmpresa.status == "aceita",
            ((ConexaoEmpresa.tenant_id_origem == a) & (ConexaoEmpresa.tenant_id_destino == b))
            | ((ConexaoEmpresa.tenant_id_origem == b) & (ConexaoEmpresa.tenant_id_destino == a)),
        )
        .first()
        is not None
    )
