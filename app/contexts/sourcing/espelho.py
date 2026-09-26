"""Espelho e backfill das tabelas unificadas (S3, D-055) — parte neutra.

As tabelas antigas continuam a fonte da verdade. Cada lado declara como uma
linha antiga vira uma linha nova (mapeamento) e chama estas funções com o
**seu** lado; o núcleo não conhece modelo de nenhum lado e nunca muda o
`lado` de uma linha já gravada.

- `gravar`: upsert pela origem (`origem_tabela`, `origem_id`[, índice]).
  Referências a pais vêm como origem (`processo_origem=("licitacao", 7)`) e
  são resolvidas aqui, sempre dentro do mesmo lado.
- `apagar`: remove a linha e as filhas (sem CASCADE no banco, por convenção).
- Falha de espelho nunca derruba a escrita do usuário: roda em SAVEPOINT e
  vira log `SOURCING_ESPELHO_FALHOU`; o backfill corrige. No modo ESTRITO
  (testes), a falha sobe.
"""

import logging
from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy import and_, delete, insert, inspect, select, update
from sqlalchemy.engine import Connection

from app.contexts.sourcing.tipos import Lado
from app.core.config import settings
from app.models.sourcing import (
    ContratoSourcing,
    DocumentoSourcing,
    EventoContratoSourcing,
    EventoSourcing,
    ProcessoSourcing,
    RequisitoSourcing,
)

logger = logging.getLogger("b2bon.sourcing")

TABELAS = {
    "processo": ProcessoSourcing.__table__,
    "contrato": ContratoSourcing.__table__,
    "documento": DocumentoSourcing.__table__,
    "requisito": RequisitoSourcing.__table__,
    "evento": EventoSourcing.__table__,
    "evento_contrato": EventoContratoSourcing.__table__,
}
# chave de referência → (tabela do pai, coluna na filha)
REFERENCIAS = {
    "processo_origem": ("processo", "processo_id"),
    "contrato_origem": ("contrato", "contrato_id"),
    "documento_origem": ("documento", "documento_id"),
}
# filhas de cada tabela (para apagar sem CASCADE)
FILHAS = {
    "processo": (("documento", "processo_id"), ("requisito", "processo_id"), ("evento", "processo_id"), ("contrato", "processo_id")),
    "contrato": (("documento", "contrato_id"), ("evento_contrato", "contrato_id")),
    "documento": (("requisito", "documento_id"),),
}


class EspelhoInconsistente(Exception):
    pass


def carregado(objeto, atributo: str):
    """Valor já carregado no objeto, sem disparar consulta (default do banco
    ainda não lido durante o flush vira None; o backfill completa)."""
    return inspect(objeto).dict.get(atributo)


def modo_leitura_dupla() -> str:
    return (settings.sourcing_leitura_dupla or "COMPARAR").upper()


def _id_por_origem(conn: Connection, tabela: str, lado: Lado, origem: tuple[str, int] | None) -> int | None:
    if origem is None or origem[1] is None:
        return None
    t = TABELAS[tabela]
    linha = conn.execute(select(t.c.id, t.c.lado).where(t.c.origem_tabela == origem[0], t.c.origem_id == origem[1])).first()
    if linha is None:
        return None
    if linha.lado != lado.value:  # nunca liga filha de um lado a pai do outro
        raise EspelhoInconsistente(f"{tabela} de origem {origem} é {linha.lado}, esperado {lado.value}")
    return linha.id


def gravar(conn: Connection, tabela: str, lado: Lado, origem_tabela: str, origem_id: int, valores: dict,
           origem_indice: int | None = None) -> int:
    """Upsert pela origem. Nunca altera `lado` de uma linha existente."""
    t = TABELAS[tabela]
    dados = {k: v for k, v in valores.items() if k not in REFERENCIAS and not (k == "criado_em" and v is None)}
    for chave, (tabela_pai, coluna) in REFERENCIAS.items():
        if chave in valores:
            dados[coluna] = _id_por_origem(conn, tabela_pai, lado, valores[chave])
    filtro = [t.c.origem_tabela == origem_tabela, t.c.origem_id == origem_id]
    if origem_indice is not None:
        filtro.append(t.c.origem_indice == origem_indice)
    existente = conn.execute(select(t.c.id, t.c.lado).where(and_(*filtro))).first()
    dados["espelhado_em"] = datetime.now(UTC).replace(tzinfo=None)
    if existente is not None:
        if existente.lado != lado.value:
            raise EspelhoInconsistente(f"{tabela} {origem_tabela}:{origem_id} é {existente.lado}, esperado {lado.value}")
        conn.execute(update(t).where(t.c.id == existente.id).values(**dados))
        return existente.id
    dados.update(lado=lado.value, origem_tabela=origem_tabela, origem_id=origem_id)
    if origem_indice is not None:
        dados["origem_indice"] = origem_indice
    elif "origem_indice" in t.c:
        dados["origem_indice"] = 0
    return conn.execute(insert(t).values(**dados)).inserted_primary_key[0]


def _apagar_ids(conn: Connection, tabela: str, ids: list[int]) -> None:
    if not ids:
        return
    for filha, coluna in FILHAS.get(tabela, ()):
        t_filha = TABELAS[filha]
        filhos = [r.id for r in conn.execute(select(t_filha.c.id).where(t_filha.c[coluna].in_(ids)))]
        if filha == "contrato" and coluna == "processo_id":  # contrato sobrevive ao processo (vira avulso)
            conn.execute(update(t_filha).where(t_filha.c.id.in_(filhos)).values(processo_id=None))
            continue
        _apagar_ids(conn, filha, filhos)
    t = TABELAS[tabela]
    conn.execute(delete(t).where(t.c.id.in_(ids)))


def apagar(conn: Connection, tabela: str, lado: Lado, origem_tabela: str, origem_id: int) -> None:
    t = TABELAS[tabela]
    ids = [r.id for r in conn.execute(select(t.c.id).where(
        t.c.origem_tabela == origem_tabela, t.c.origem_id == origem_id, t.c.lado == lado.value))]
    _apagar_ids(conn, tabela, ids)


def substituir_requisitos(conn: Connection, lado: Lado, origem_tabela: str, origem_id: int, itens: list[dict]) -> None:
    """Requisitos guardados como lista numa linha de origem (achados em JSON):
    a lista inteira é regravada, cada item pela sua posição."""
    t = TABELAS["requisito"]
    conn.execute(delete(t).where(t.c.origem_tabela == origem_tabela, t.c.origem_id == origem_id, t.c.lado == lado.value,
                                 t.c.origem_indice >= len(itens)))
    for indice, valores in enumerate(itens):
        gravar(conn, "requisito", lado, origem_tabela, origem_id, valores, origem_indice=indice)


def apagar_orfaos(conn: Connection, tabela: str, lado: Lado, origem_tabela: str, ids_vivos: set[int]) -> int:
    """Backfill: remove linhas cuja origem não existe mais."""
    t = TABELAS[tabela]
    mortos = [r.id for r in conn.execute(select(t.c.id, t.c.origem_id).where(
        t.c.origem_tabela == origem_tabela, t.c.lado == lado.value)) if r.origem_id not in ids_vivos]
    _apagar_ids(conn, tabela, mortos)
    return len(mortos)


def protegido(conn: Connection, descricao: str, operacao: Callable[[], None]) -> None:
    """Executa o espelho sem derrubar a escrita de quem chamou (SAVEPOINT)."""
    try:
        with conn.begin_nested():
            operacao()
    except Exception:
        if modo_leitura_dupla() == "ESTRITA":
            raise
        logger.exception("SOURCING_ESPELHO_FALHOU %s", descricao)


# --- Backfill: cada lado registra o seu sincronizador --------------------------------
_SINCRONIZADORES: dict[Lado, Callable] = {}


def registrar_sincronizador(lado: Lado, funcao: Callable) -> None:
    _SINCRONIZADORES[lado] = funcao


def sincronizar_todos(db, tenant_id: str | None = None) -> dict:
    """Backfill idempotente dos dois lados (cada um com o seu lado fixo)."""
    return {lado.value: funcao(db, tenant_id) for lado, funcao in sorted(_SINCRONIZADORES.items())}
