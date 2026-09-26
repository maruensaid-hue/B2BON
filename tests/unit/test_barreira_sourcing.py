"""Fitness function da barreira por repositório (S2, D-055, §2.3 do
`18_STRATEGIC_SOURCING.md`). Roda junto com `test_barreira_buy_sell.py`
(a regra antiga, por tabela) até a S3 trocar as tabelas.

1. As tabelas de cada lado só são lidas pelo próprio contexto, pela API
   desse lado e por `app/models`. Quem está fora (FinOps, Analytics…) lê
   pelo repositório do lado — nunca pelas tabelas.
2. O núcleo `sourcing` não importa modelo nem contexto de nenhum dos lados:
   ele não pode virar ponte entre Buy e Sell.
3. Cada lado implementa o protocolo do núcleo com o lado **fixo**.
4. Toda ferramenta do agente registrada por um lado declara esse lado.
"""

import ast
import re
from pathlib import Path

from app.contexts.bids import contract as bids
from app.contexts.shared import ferramentas
from app.contexts.sourcing import contract as sourcing

RAIZ = Path(__file__).resolve().parents[2]
APP = RAIZ / "app"

TABELAS = {
    "venda": {
        "tabelas": {"licitacao", "documento_licitacao", "requisito_licitacao", "contrato_venda_publica", "decisao_go_no_go",
                    "documento_cofre"},
        "permitidos": (APP / "contexts" / "bids", APP / "api" / "v1" / "bids.py", APP / "models"),
    },
    "compra": {
        "tabelas": {"orgao_publico", "unidade_compras", "plano_contratacao", "item_pca", "demanda_compra", "processo_contratacao",
                    "evento_processo", "fornecedor_compras", "contrato_compra", "evento_contrato_compra", "pesquisa_preco",
                    "documento_compras"},
        "permitidos": (APP / "contexts" / "procurement", APP / "api" / "v1" / "procurement.py", APP / "models"),
    },
}


def _arquivos(permitidos=()) -> list[Path]:
    return [p for p in APP.rglob("*.py")
            if "__pycache__" not in p.parts and not any(p == x or x in p.parents for x in permitidos)]


def _imports(arquivo: Path) -> list[str]:
    modulos = []
    for no in ast.walk(ast.parse(arquivo.read_text(encoding="utf-8"))):
        if isinstance(no, ast.Import):
            modulos.extend(a.name for a in no.names)
        elif isinstance(no, ast.ImportFrom) and no.module:
            modulos.append(no.module)
    return modulos


def test_tabelas_de_cada_lado_so_pelo_proprio_lado_ou_pelo_repositorio():
    violacoes = []
    for lado, regra in TABELAS.items():
        padrao_sql = re.compile(r"\b(" + "|".join(sorted(regra["tabelas"])) + r")\b")
        for arquivo in _arquivos(regra["permitidos"]):
            for modulo in _imports(arquivo):
                partes = modulo.split(".")
                if partes[:2] == ["app", "models"] and len(partes) > 2 and partes[2] in regra["tabelas"]:
                    violacoes.append(f"[{lado}] {arquivo.relative_to(RAIZ)} importa {modulo}")
            for no in ast.walk(ast.parse(arquivo.read_text(encoding="utf-8"))):
                if isinstance(no, ast.Constant) and isinstance(no.value, str) and padrao_sql.search(no.value) and (
                        "select" in no.value.lower() or " from " in no.value.lower()):
                    violacoes.append(f"[{lado}] {arquivo.relative_to(RAIZ)} cita tabela em SQL: {no.value[:60]!r}")
    assert violacoes == [], "\n".join(violacoes)


def test_nucleo_de_sourcing_nao_importa_nenhum_dos_lados():
    """O núcleo só conhece as próprias tabelas unificadas (S3)."""
    proibidos = ("app.models", "app.contexts.bids", "app.contexts.procurement")
    violacoes = [
        f"{arquivo.relative_to(RAIZ)} importa {modulo}"
        for arquivo in (APP / "contexts" / "sourcing").rglob("*.py")
        for modulo in _imports(arquivo)
        if modulo.startswith(proibidos) and modulo != "app.models.sourcing"
    ]
    assert violacoes == [], "\n".join(violacoes)


def test_tabelas_unificadas_so_pelo_nucleo():
    """S3: as tabelas `*_sourcing` guardam os dois lados; só o núcleo (que
    sempre recebe o lado de quem chama) as lê ou escreve."""
    permitidos = (APP / "contexts" / "sourcing", APP / "models")
    tabelas = r"\b(processo|contrato|documento|requisito|evento|evento_contrato)_sourcing\b"
    violacoes = []
    for arquivo in _arquivos(permitidos):
        if "app.models.sourcing" in _imports(arquivo):
            violacoes.append(f"{arquivo.relative_to(RAIZ)} importa app.models.sourcing")
        for no in ast.walk(ast.parse(arquivo.read_text(encoding="utf-8"))):
            if isinstance(no, ast.Constant) and isinstance(no.value, str) and re.search(tabelas, no.value) and (
                    "select" in no.value.lower() or " from " in no.value.lower() or "update" in no.value.lower()):
                violacoes.append(f"{arquivo.relative_to(RAIZ)} cita tabela unificada em SQL: {no.value[:60]!r}")
    assert violacoes == [], "\n".join(violacoes)


def test_cada_lado_so_usa_o_proprio_lado_com_o_nucleo():
    """Quem passa `Lado.COMPRA` ao núcleo é só o comprador; `Lado.VENDA`, só o vendedor."""
    donos = {"COMPRA": (APP / "contexts" / "procurement", APP / "api" / "v1" / "procurement.py"),
             "VENDA": (APP / "contexts" / "bids", APP / "api" / "v1" / "bids.py")}
    nucleo = (APP / "contexts" / "sourcing",)
    violacoes = []
    for membro, permitidos in donos.items():
        for arquivo in _arquivos(permitidos + nucleo):
            for no in ast.walk(ast.parse(arquivo.read_text(encoding="utf-8"))):
                if isinstance(no, ast.Attribute) and no.attr == membro and isinstance(no.value, ast.Attribute | ast.Name) and (
                        getattr(no.value, "attr", None) == "Lado" or getattr(no.value, "id", None) == "Lado"):
                    violacoes.append(f"{arquivo.relative_to(RAIZ)} usa Lado.{membro}")
    assert violacoes == [], "\n".join(violacoes)


def test_repositorio_de_compra_so_no_lado_comprador():
    permitidos = (APP / "contexts" / "procurement", APP / "api" / "v1" / "procurement.py")
    def referencia(arquivo: Path) -> bool:
        for no in ast.walk(ast.parse(arquivo.read_text(encoding="utf-8"))):
            if (isinstance(no, ast.Name) and no.id == "RepositorioCompra") or (
                    isinstance(no, ast.Attribute) and no.attr == "RepositorioCompra"):
                return True
        return any(m.startswith("app.contexts.procurement") for m in _imports(arquivo))

    violacoes = [f"{arquivo.relative_to(RAIZ)}" for arquivo in _arquivos(permitidos) if referencia(arquivo)]
    assert violacoes == [], "\n".join(violacoes)


def test_cada_lado_implementa_o_protocolo_com_o_lado_fixo():
    from app.contexts.procurement.repositorio import COMPRA

    Lado = sourcing.tipos.Lado
    assert isinstance(bids.repositorio.VENDA, sourcing.repositorio.RepositorioSourcing)
    assert isinstance(COMPRA, sourcing.repositorio.RepositorioSourcing)
    assert (bids.repositorio.VENDA.lado, COMPRA.lado) == (Lado.VENDA, Lado.COMPRA)


def test_ferramentas_do_agente_declaram_o_lado_de_quem_as_registra():
    import app.contexts.procurement.contract  # noqa: F401 — registra as ferramentas do comprador

    registro = ferramentas._REGISTRO
    por_prefixo = {"bids.": "SELL", "procurement.": "BUY"}
    erradas = [f"{nome}: {f.lado}" for nome, f in registro.items() for prefixo, lado in por_prefixo.items()
               if nome.startswith(prefixo) and f.lado != lado]
    assert any(nome.startswith("procurement.") for nome in registro) and any(nome.startswith("bids.") for nome in registro)
    assert erradas == [], "\n".join(erradas)
