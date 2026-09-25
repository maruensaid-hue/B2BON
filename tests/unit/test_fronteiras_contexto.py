"""Fitness function das fronteiras de contexto (Fase 1, Master Prompt §9/§10).

Regras verificadas por AST em todo `app/`:

1. Código de fora de um contexto só importa `app.contexts.<ctx>.contract`
   (ou o pacote `app.contexts.<ctx>` para obter `contract`); `shared` é
   Shared Kernel, livre para todos.
2. O MAP não lê o ORM de pipeline do CRM nem `crm_service`: vai pelo
   `MapDataSource` → `app.contexts.crm.contract`.
3. Regressões dos acoplamentos corrigidos na Fase 1 (C2): o serviço do
   MAP não volta a importar `crm_service`.
"""

import ast
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
APP = RAIZ / "app"
CONTEXTOS = {p.name for p in (APP / "contexts").iterdir() if p.is_dir() and not p.name.startswith("__")}


def _imports(arquivo: Path) -> list[str]:
    arvore = ast.parse(arquivo.read_text(encoding="utf-8"))
    modulos: list[str] = []
    for no in ast.walk(arvore):
        if isinstance(no, ast.Import):
            modulos.extend(alias.name for alias in no.names)
        elif isinstance(no, ast.ImportFrom) and no.module:
            modulos.append(no.module)
            modulos.extend(f"{no.module}.{alias.name}" for alias in no.names)
    return modulos


def _contexto_do_arquivo(arquivo: Path) -> str | None:
    partes = arquivo.relative_to(APP).parts
    if len(partes) >= 2 and partes[0] == "contexts" and partes[1] in CONTEXTOS:
        return partes[1]
    return None


def _arquivos_python() -> list[Path]:
    return [p for p in APP.rglob("*.py") if "__pycache__" not in p.parts]


def test_so_o_contrato_de_um_contexto_e_importado_de_fora_dele():
    violacoes = []
    for arquivo in _arquivos_python():
        origem = _contexto_do_arquivo(arquivo)
        for modulo in _imports(arquivo):
            partes = modulo.split(".")
            if partes[:2] != ["app", "contexts"] or len(partes) < 4:
                continue
            alvo, submodulo = partes[2], partes[3]
            if alvo == "shared" or alvo == origem or submodulo == "contract":
                continue
            violacoes.append(f"{arquivo.relative_to(RAIZ)} importa {modulo}")
    assert violacoes == [], "\n".join(violacoes)


def test_map_nao_le_orm_de_pipeline_do_crm():
    proibidos = {"app.models.negocio", "app.models.estagio_funil", "app.models.custo_aquisicao", "app.services.crm_service"}
    violacoes = []
    for arquivo in (APP / "contexts" / "map").rglob("*.py"):
        for modulo in _imports(arquivo):
            if any(modulo == p or modulo.startswith(p + ".") for p in proibidos):
                violacoes.append(f"{arquivo.relative_to(RAIZ)} importa {modulo}")
    assert violacoes == [], "\n".join(violacoes)


def test_servico_do_map_nao_depende_mais_do_crm_service():
    for nome in ("saude_conta_service.py", "metricas_service.py", "motor_service.py"):
        modulos = _imports(APP / "services" / nome)
        assert "app.services.crm_service" not in modulos, nome
        assert not any(m == "app.services.crm_service" or m.endswith(".crm_service") for m in modulos), nome


def test_crm_service_nao_importa_mais_servicos_do_map():
    modulos = _imports(APP / "services" / "crm_service.py")
    for proibido in ("app.services.saude_conta_service", "app.services.metricas_service"):
        assert proibido not in modulos
