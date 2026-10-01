"""Marca a requisição corrente como sessão de demonstração (D-082/D-083).

O middleware liga a marca quando o token é de demonstração; os provedores (`app/api/deps.py`) a consultam para trocar
todo serviço externo — e-mail, agenda, robô de reunião, enriquecimento, busca web, pagamento, acesso a sites, grafo —
por simulações. Assim nenhuma ação da demonstração sai da plataforma nem gera custo com terceiros.
"""

from contextvars import ContextVar

_demo: ContextVar[bool] = ContextVar("b2bon_demo", default=False)


def ligar() -> None:
    _demo.set(True)


def ativo() -> bool:
    return _demo.get()
