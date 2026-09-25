"""Corporate Brain do tenant (Fase 4, Master Prompt §15).

Conhecimento institucional explícito (produtos, cases, objeções,
concorrentes, personas, estratégia, ICP, aprendizados), sempre escopado
ao tenant. Busca por palavras-chave com normalização de acento — sem
embeddings nesta fase (decisão D-017: o volume por tenant é pequeno e
pgvector exigiria extensão no Neon; reavaliar na Fase 17).
"""

import re
import unicodedata

from sqlalchemy.orm import Session

from app.contexts.shared.canonical.base import DataClassification, DataOrigin
from app.models.conhecimento_corporativo import ConhecimentoCorporativo
from app.services import auditoria_service
from app.services.errors import NaoEncontrado, ValidacaoFalhou

TIPOS = frozenset({"produto", "servico", "oferta", "case", "objecao", "concorrente", "persona", "estrategia", "icp", "aprendizado", "politica", "outro"})
VISIBILIDADES = frozenset({"interno", "rede"})
_STOPWORDS = frozenset("a o e de da do das dos em no na nos nas um uma para por com que se os as ao aos ou sua seu".split())


def _normalizar(texto: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return sem_acento.lower()


def _termos(texto: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]{3,}", _normalizar(texto)) if t not in _STOPWORDS}


def criar(db: Session, tenant_id: str, usuario_id: int | None, dados: dict) -> ConhecimentoCorporativo:
    if dados.get("tipo") not in TIPOS:
        raise ValidacaoFalhou(f"Tipo inválido. Válidos: {sorted(TIPOS)}")
    if dados.get("visibilidade", "interno") not in VISIBILIDADES:
        raise ValidacaoFalhou("Visibilidade deve ser 'interno' ou 'rede'.")
    classificacao = DataClassification(dados.get("classificacao", "INTERNAL"))
    if dados.get("visibilidade") == "rede" and classificacao not in (DataClassification.PUBLIC, DataClassification.INTERNAL):
        raise ValidacaoFalhou("Item CONFIDENTIAL/RESTRICTED não pode ter visibilidade 'rede'.")
    item = ConhecimentoCorporativo(
        tenant_id=tenant_id,
        tipo=dados["tipo"],
        titulo=dados["titulo"].strip()[:200],
        conteudo=dados["conteudo"].strip()[:8000],
        origem=DataOrigin(dados.get("origem", "INTERNAL")).value,
        classificacao=classificacao.value,
        visibilidade=dados.get("visibilidade", "interno"),
        fonte=dados.get("fonte"),
        evidencia=dados.get("evidencia") or [],
        ativo=True,
        criado_por_usuario_id=usuario_id,
    )
    db.add(item)
    db.flush()
    auditoria_service.registrar(db, tenant_id, "conhecimento_criado", "conhecimento_corporativo", item.id, str(usuario_id) if usuario_id else None, {"tipo": item.tipo})
    db.commit()
    db.refresh(item)
    return item


def obter(db: Session, tenant_id: str, item_id: int) -> ConhecimentoCorporativo:
    item = db.query(ConhecimentoCorporativo).filter_by(id=item_id, tenant_id=tenant_id).one_or_none()
    if item is None:
        raise NaoEncontrado(f"Conhecimento {item_id} não encontrado")
    return item


def listar(db: Session, tenant_id: str, tipo: str | None = None) -> list[ConhecimentoCorporativo]:
    query = db.query(ConhecimentoCorporativo).filter_by(tenant_id=tenant_id, ativo=True)
    if tipo:
        query = query.filter_by(tipo=tipo)
    return query.order_by(ConhecimentoCorporativo.id.desc()).all()


def arquivar(db: Session, tenant_id: str, usuario_id: int | None, item_id: int) -> None:
    item = obter(db, tenant_id, item_id)
    item.ativo = False
    auditoria_service.registrar(db, tenant_id, "conhecimento_arquivado", "conhecimento_corporativo", item.id, str(usuario_id) if usuario_id else None, {})
    db.commit()


def buscar(
    db: Session,
    tenant_id: str,
    consulta: str,
    *,
    visibilidades: frozenset[str] = VISIBILIDADES,
    classificacoes: frozenset[str] = frozenset(c.value for c in DataClassification),
    limite: int = 5,
) -> list[tuple[ConhecimentoCorporativo, int]]:
    """Itens do PRÓPRIO tenant, filtrados por visibilidade/classificação,
    ordenados por aderência à consulta. Sem aderência, não retorna nada:
    melhor contexto vazio do que contexto irrelevante (§58)."""
    termos = _termos(consulta)
    if not termos:
        return []
    candidatos = (
        db.query(ConhecimentoCorporativo)
        .filter(
            ConhecimentoCorporativo.tenant_id == tenant_id,
            ConhecimentoCorporativo.ativo.is_(True),
            ConhecimentoCorporativo.visibilidade.in_(visibilidades),
            ConhecimentoCorporativo.classificacao.in_(classificacoes),
        )
        .all()
    )
    pontuados = []
    for item in candidatos:
        pontos = 2 * len(termos & _termos(item.titulo)) + len(termos & _termos(item.conteudo)) + len(termos & _termos(item.tipo))
        if pontos:
            pontuados.append((item, pontos))
    pontuados.sort(key=lambda par: (-par[1], par[0].id))
    return pontuados[:limite]
