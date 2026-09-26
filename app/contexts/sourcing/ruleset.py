"""Rulesets declarativos (S4, D-055) — motor neutro.

Um ruleset reúne as regras de um regime (`PUBLIC_PROCUREMENT_BR_14133@1`):
versão, vigência e fonte (plano unificado §22), documentos esperados por etapa
e parâmetros com valor padrão (a configuração). Parâmetro
configurado pelo cliente (ex.: `orgao.parametros`) prevalece sobre o padrão;
parâmetro sem padrão (`None`) e não configurado fica sem avaliação — nunca é
inventado.
"""

from dataclasses import dataclass, field
from datetime import date


@dataclass(frozen=True)
class Ruleset:
    codigo: str
    descricao: str
    fonte: str  # de onde vêm as regras (norma, política do comprador)
    vigente_desde: date | None = None  # None: sem norma com vigência (ex.: regra privada)
    documentos_esperados: dict[str, tuple[str, ...]] = field(default_factory=dict)
    parametros: dict[str, float | int | None] = field(default_factory=dict)

    def __post_init__(self):
        if "@" not in self.codigo:
            raise ValueError(f"{self.codigo}: o código leva a versão (`NOME@n`)")
        if not self.fonte.strip():
            raise ValueError(f"{self.codigo}: informe a fonte das regras")

    @property
    def versao(self) -> int:
        return int(self.codigo.rsplit("@", 1)[1])

    def __hash__(self):
        return hash(self.codigo)

    def documentos(self, etapa: str) -> tuple[str, ...]:
        return self.documentos_esperados.get(etapa, ())

    def parametro(self, nome: str, configurados: dict | None = None):
        """Valor configurado, senão o padrão do ruleset. Nome fora do ruleset é erro de programação."""
        if nome not in self.parametros:
            raise KeyError(f"{self.codigo} não declara o parâmetro {nome}")
        return (configurados or {}).get(nome, self.parametros[nome])


_REGISTRO: dict[str, Ruleset] = {}


def registrar(ruleset: Ruleset) -> Ruleset:
    existente = _REGISTRO.get(ruleset.codigo)
    if existente is not None and existente != ruleset:
        raise ValueError(f"{ruleset.codigo} já registrado com outra definição (crie uma nova versão)")
    _REGISTRO[ruleset.codigo] = ruleset
    return ruleset


def obter(codigo: str) -> Ruleset:
    return _REGISTRO[codigo]


def codigos() -> set[str]:
    return set(_REGISTRO)
