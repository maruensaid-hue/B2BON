"""Regras de visibilidade da Business Network num lugar só (GATE da Fase 7).

- Bloqueio (em qualquer direção) esconde conteúdo entre as duas empresas:
  feed, necessidades (intents) e arestas do grafo.
- Visibilidade de conteúdo: `publica` (qualquer empresa da rede),
  `conexoes` (as partes e quem tem conexão aceita com o autor), `privada`
  (só o autor).
- Dado de CRM (contas, negócios, necessidades, margens) nunca é lido por
  este contexto.
"""

from sqlalchemy.orm import Session

from app.models.conexao_empresa import ConexaoEmpresa

VISIBILIDADES = ("publica", "conexoes", "privada")


def _conexoes(db: Session, tenant_id: str, status: str) -> set[str]:
    linhas = (
        db.query(ConexaoEmpresa.tenant_id_origem, ConexaoEmpresa.tenant_id_destino)
        .filter(
            ConexaoEmpresa.status == status,
            (ConexaoEmpresa.tenant_id_origem == tenant_id) | (ConexaoEmpresa.tenant_id_destino == tenant_id),
        )
        .all()
    )
    return {destino if origem == tenant_id else origem for origem, destino in linhas}


def bloqueados(db: Session, tenant_id: str) -> set[str]:
    """Empresas com bloqueio entre elas e `tenant_id`, em qualquer direção."""
    return _conexoes(db, tenant_id, "bloqueada")


def conectados(db: Session, tenant_id: str) -> set[str]:
    return _conexoes(db, tenant_id, "aceita")


def pode_ver(
    db: Session,
    consultante: str,
    autor: str,
    visibilidade: str,
    *,
    partes: tuple[str | None, ...] = (),
    cache: dict | None = None,
) -> bool:
    """`autor` é quem criou o conteúdo; `partes`, outras empresas citadas
    nele (ex.: destino de uma aresta), que veem o que for `conexoes`."""
    if consultante == autor:
        return True
    cache = cache if cache is not None else {}
    if "bloqueados" not in cache:
        cache["bloqueados"] = bloqueados(db, consultante)
    if autor in cache["bloqueados"]:
        return False
    if visibilidade == "publica":
        return True
    if visibilidade == "conexoes":
        if consultante in partes:
            return True
        if "conectados" not in cache:
            cache["conectados"] = conectados(db, consultante)
        return autor in cache["conectados"]
    return False


def perfis_visiveis(db: Session, consultante: str) -> list:
    """Empresas que o consultante pode encontrar/receber como match (Fase 8):
    exclui a própria, as bloqueadas e as fora do diretório que não são conexão."""
    from app.models.perfil_empresa import PerfilEmpresa

    bloqueadas = bloqueados(db, consultante)
    perfis = db.query(PerfilEmpresa).filter(PerfilEmpresa.tenant_id != consultante).all()
    conectadas = conectados(db, consultante) if any(not p.visivel_no_diretorio for p in perfis) else set()
    return [
        p for p in perfis
        if p.tenant_id not in bloqueadas and (p.visivel_no_diretorio or p.tenant_id in conectadas)
    ]
