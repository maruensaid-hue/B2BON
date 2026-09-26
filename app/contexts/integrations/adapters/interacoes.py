"""Interações por conta a partir de atividades concluídas (TD-092, Phase J2): regra comum aos conectores que só
têm "atividade/tarefa feita" como sinal de contato (Pipedrive, RD Station)."""

from collections.abc import Callable, Iterable

from app.contexts.integrations.contract import Page
from app.contexts.shared.canonical.commercial import Activity, Interaction


def por_conta(registros: Iterable[dict], atividade: Callable[[dict], Activity], cid: Callable[[str, object], str],
              tenant_id: str) -> dict[str, list[Interaction]]:
    """Atividade concluída com conta = um contato registrado com a conta."""
    resultado: dict[str, list[Interaction]] = {}
    for registro in registros:
        convertida = atividade(registro)
        if convertida.account_id:
            resultado.setdefault(convertida.account_id, []).append(Interaction(
                id=cid("interaction", registro["id"]), tenant_id=tenant_id, source=convertida.source,
                account_id=convertida.account_id, kind="contato", description=convertida.description or None,
                created_at=convertida.created_at))
    return resultado


def pagina(interacoes: dict[str, list[Interaction]], account_id: str | None) -> Page:
    if account_id is not None:
        return Page(items=list(interacoes.get(account_id, [])))
    return Page(items=[i for itens in interacoes.values() for i in itens])
