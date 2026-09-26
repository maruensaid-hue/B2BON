"""Matching Engine — base compartilhada de aderência (plano de sourcing S1, D-055).

Toda aderência da plataforma (ICP, oferta, intenção, fornecedor, RFP) é uma
lista de critérios com peso. Cada critério diz se atende (`True`), não atende
(`False`) ou se falta dado (`None`). Falta de dado nunca vira "não atende"
em silêncio: ela aparece em `faltantes` e reduz a confiança.

Estratégias declaram os critérios; esta base só combina. Migração por toque:
cada estratégia existente passa a usar a base quando o código dela for
mexido, com teste de paridade (ICP foi a primeira).
"""

from collections.abc import Iterable
from dataclasses import dataclass, field

from app.providers.account_data.receita_federal_downloader import normalizar_cnae


@dataclass(frozen=True)
class Criterio:
    nome: str
    peso: float
    atende: bool | None  # None = dado ausente
    motivo: str | None = None


@dataclass(frozen=True)
class Resultado:
    pontuacao: float
    motivos: list[str] = field(default_factory=list)
    faltantes: list[str] = field(default_factory=list)
    confianca: str = "alta"  # alta (nada faltando) | media (1 faltando) | baixa (2+)


def combinar(criterios: Iterable[Criterio]) -> Resultado:
    """Soma os pesos dos critérios atendidos (arredondado a 2 casas)."""
    lista = list(criterios)
    pontuacao = sum(c.peso for c in lista if c.atende)
    faltantes = [c.nome for c in lista if c.atende is None]
    confianca = "alta" if not faltantes else ("media" if len(faltantes) == 1 else "baixa")
    return Resultado(round(pontuacao, 2), [c.motivo for c in lista if c.atende and c.motivo], faltantes, confianca)


# --- Estratégia: aderência ao ICP (PREDATOR e rede) -------------------------------
PESO_CNAE = 0.5
PESO_UF = 0.3
PESO_PORTE = 0.2


def criterios_icp(icp_cnaes: Iterable[str], icp_ufs: Iterable[str], icp_porte: str | None,
                  cnae: str | None, uf: str | None, porte: str | None) -> list[Criterio]:
    """CNAE 0,5 + UF 0,3 + porte 0,2. CNAE comparado em dígitos puros dos dois
    lados (o ICP guarda como digitado; a Receita e o perfil podem vir pontuados)."""
    cnaes = {normalizar_cnae(c) for c in icp_cnaes if c}
    ufs = {u.upper() for u in icp_ufs if u}
    return [
        Criterio("cnae_principal", PESO_CNAE, None if not cnae else normalizar_cnae(cnae) in cnaes,
                 f"CNAE principal ({cnae}) está entre os CNAEs do ICP."),
        Criterio("sede_uf", PESO_UF, None if not uf else uf.upper() in ufs, f"Sede em {uf} está entre as UFs do ICP."),
        Criterio("porte", PESO_PORTE, None if not porte else bool(icp_porte) and porte == icp_porte,
                 f"Porte ({porte}) corresponde ao porte do ICP."),
    ]
