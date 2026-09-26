"""Leitura pelas tabelas unificadas (Phase J1, preparação da S6) — parte neutra.

Com `sourcing_leitura_fonte = UNIFICADA`, as leituras de listagem dos repositórios por lado vêm de
`*_sourcing`, sempre filtradas por tenant **e** pelo lado de quem pergunta; cada lado devolve as linhas no
formato antigo (mesmos ids e campos), então a API não muda. Padrão ANTIGA: nada muda até o portão operacional
(backfill em produção e uma release sem SOURCING_DIVERGENCIA, TD-087/088). Escritas e `obter_processo`
(usado para alterar o registro) continuam nas tabelas antigas até a S6 mover a escrita.
"""

from datetime import datetime

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.contexts.sourcing.espelho import TABELAS
from app.contexts.sourcing.paridade import origens
from app.contexts.sourcing.tipos import Lado
from app.core.config import settings

__all__ = ["filhas", "origens", "processos_por_prazo", "unificada"]


def unificada() -> bool:
    return (settings.sourcing_leitura_fonte or "ANTIGA").upper() == "UNIFICADA"


def processos_por_prazo(db: Session, lado: Lado, tenant_id: str, origem_tabela: str, quantidade: int, posicao: dict | None = None,
                        status: str | None = None) -> list[dict]:
    """Mesma ordem e keyset da listagem antiga: prazo mais próximo primeiro (sem prazo no fim), depois o id de
    origem decrescente. Devolve `quantidade + 1` linhas para o fatiamento saber se há próxima página."""
    p = TABELAS["processo"]
    consulta = select(p).where(p.c.tenant_id == tenant_id, p.c.lado == lado.value, p.c.origem_tabela == origem_tabela)
    if status:
        consulta = consulta.where(p.c.status == status)
    if posicao is not None:
        ultimo_id = int(posicao["id"])
        if posicao.get("prazo") is None:
            consulta = consulta.where(p.c.prazo.is_(None), p.c.origem_id < ultimo_id)
        else:
            prazo = datetime.fromisoformat(posicao["prazo"])
            consulta = consulta.where(or_(p.c.prazo.is_(None), p.c.prazo > prazo, and_(p.c.prazo == prazo, p.c.origem_id < ultimo_id)))
    consulta = consulta.order_by(p.c.prazo.is_(None), p.c.prazo, p.c.origem_id.desc()).limit(quantidade + 1)
    return [dict(linha) for linha in db.execute(consulta).mappings()]


def filhas(db: Session, tabela: str, lado: Lado, tenant_id: str, processo_origem: tuple[str, int], origem_tabela: str) -> list[dict]:
    """Linhas de `tabela` (documento, requisito…) de um processo identificado pela origem, só do lado pedido."""
    p, t = TABELAS["processo"], TABELAS[tabela]
    consulta = (select(t).join(p, t.c.processo_id == p.c.id)
                .where(p.c.tenant_id == tenant_id, p.c.lado == lado.value, p.c.origem_tabela == processo_origem[0],
                       p.c.origem_id == processo_origem[1], t.c.tenant_id == tenant_id, t.c.lado == lado.value,
                       t.c.origem_tabela == origem_tabela)
                .order_by(t.c.origem_id))
    return [dict(linha) for linha in db.execute(consulta).mappings()]
