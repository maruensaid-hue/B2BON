"""Workflow declarativo de processos de sourcing (S4, D-055) — motor neutro.

Cada lado declara o seu fluxo (estados, inicial, finais e transições) e o
registra aqui com o código versionado (`PUBLIC_TENDER_SELL@1`). O núcleo não
conhece estado de nenhum lado: só valida contra o que foi declarado.

Uma transição diz **por qual ação** um estado é alcançado e, opcionalmente,
de quais estados. A ação separa o que é mudança livre de status (`status`)
do que exige registro próprio (decisão Go/No-Go, resultado), com a mensagem
que o usuário vê quando tenta pelo caminho errado.
"""

from dataclasses import dataclass, field

from app.contexts.sourcing.tipos import Lado
from app.services.errors import RegraNegocioViolada, ValidacaoFalhou

QUALQUER = None  # transição aceita partindo de qualquer estado


@dataclass(frozen=True)
class Transicao:
    para: str
    acao: str
    de: frozenset[str] | None = QUALQUER


@dataclass(frozen=True)
class Workflow:
    codigo: str
    lado: Lado
    estados: tuple[str, ...]
    inicial: str
    finais: tuple[str, ...]
    transicoes: tuple[Transicao, ...]
    # ação exigida → mensagem para quem tenta alcançar o estado por outra ação
    mensagens: dict[str, str] = field(default_factory=dict)

    def __post_init__(self):
        desconhecidos = ({self.inicial, *self.finais} | {t.para for t in self.transicoes}
                         | {e for t in self.transicoes for e in (t.de or ())}) - set(self.estados)
        if desconhecidos:
            raise ValueError(f"{self.codigo}: estados não declarados {sorted(desconhecidos)}")
        if "@" not in self.codigo:
            raise ValueError(f"{self.codigo}: o código leva a versão (`NOME@n`)")

    def acoes_para(self, para: str) -> set[str]:
        return {t.acao for t in self.transicoes if t.para == para}

    def permite(self, de: str | None, para: str, acao: str) -> bool:
        return any(t.para == para and t.acao == acao and (t.de is QUALQUER or de in t.de) for t in self.transicoes)

    def validar(self, para: str, acao: str, de: str | None = None) -> None:
        """Recusa estado desconhecido (`ValidacaoFalhou`) e estado que só se
        alcança por outra ação ou a partir de outro estado (`RegraNegocioViolada`)."""
        if para not in self.estados:
            raise ValidacaoFalhou(f"Status inválido: {para}")
        if self.permite(de, para, acao):
            return
        exigidas = self.acoes_para(para)
        if exigidas and acao not in exigidas:
            exigida = sorted(exigidas)[0]
            raise RegraNegocioViolada(self.mensagens.get(exigida, f"{para} é registrado pela ação {exigida}."))
        raise RegraNegocioViolada(f"Transição não permitida: {de} → {para}.")


_REGISTRO: dict[str, Workflow] = {}


def registrar(workflow: Workflow) -> Workflow:
    existente = _REGISTRO.get(workflow.codigo)
    if existente is not None and existente != workflow:
        raise ValueError(f"{workflow.codigo} já registrado com outra definição (crie uma nova versão)")
    _REGISTRO[workflow.codigo] = workflow
    return workflow


def obter(codigo: str) -> Workflow:
    return _REGISTRO[codigo]


def codigos() -> set[str]:
    return set(_REGISTRO)
