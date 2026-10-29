"""O registro de RLS (D-110) classifica TODA tabela do modelo. Tabela nova sem classificação quebra este teste: ou ganha política (e migração), ou entra em PENDENTES/GLOBAIS com o motivo."""

import importlib.util
from pathlib import Path

import app.main  # noqa: F401 — registra também as tabelas que só o app importa (webhooks de parceiro, relatório)
import app.models  # noqa: F401
from app.db import rls_registro as r
from app.db.base import Base

RAIZ = Path(__file__).resolve().parents[2]


def _tem_tenant(tabela) -> bool:
    return any(c == "tenant_id" or c.startswith("tenant_id_") for c in tabela.columns.keys())


def _grupos() -> dict[str, set[str]]:
    return {
        "TENANT_DIRETO": set(r.TENANT_DIRETO),
        "DUAS_PARTES": set(r.DUAS_PARTES),
        "LEITURA_COMPARTILHADA": set(r.LEITURA_COMPARTILHADA),
        "HERDADAS": set(r.HERDADAS),
        "PENDENTES": set(r.PENDENTES),
        "GLOBAIS": set(r.GLOBAIS),
    }


def test_toda_tabela_esta_classificada_em_exatamente_um_grupo():
    todas = set(Base.metadata.tables)
    grupos = _grupos()
    classificadas = [t for g in grupos.values() for t in g]
    assert sorted(set(classificadas) ^ todas) == [], "tabela sem classificação, ou classificada e inexistente"
    repetidas = {t for t in classificadas if classificadas.count(t) > 1}
    assert not repetidas, f"tabela em mais de um grupo: {sorted(repetidas)}"


def test_tabelas_protegidas_tem_as_colunas_que_a_politica_usa():
    for tabela in r.TENANT_DIRETO:
        coluna = Base.metadata.tables[tabela].columns.get("tenant_id")
        assert coluna is not None and not coluna.nullable, f"{tabela}: RLS por tenant exige tenant_id NOT NULL (linha nula ficaria invisível)"
    for tabela, colunas in r.DUAS_PARTES.items():
        assert all(c in Base.metadata.tables[tabela].columns for c in colunas)


def test_globais_nao_tem_tenant_e_pendentes_explicam_o_motivo():
    for tabela in r.GLOBAIS:
        assert not _tem_tenant(Base.metadata.tables[tabela]), f"{tabela} tem coluna de tenant: não é global"
    for tabela, motivo in r.PENDENTES.items():
        assert len(motivo) > 15, f"{tabela}: PENDENTE sem motivo"


def test_buscas_e_contextos_de_sistema_so_citam_tabelas_que_existem():
    existentes = set(Base.metadata.tables)
    for busca in r.BUSCAS.values():
        assert {b.tabela for b in busca} <= existentes
    for nome, tabelas in r.CONTEXTOS_SISTEMA.items():
        assert set(tabelas) <= existentes, nome
        assert set(tabelas.values()) <= {"ler", "escrever"}, nome


def test_migracao_congelou_exatamente_o_registro_atual():
    """A migração tem cópia das listas; se alguém mexer num lado só, este teste acusa (tabela nova entra em migração nova, não editando esta)."""
    caminho = next((RAIZ / "alembic" / "versions").glob("e7a9c1d3f5b8_*.py"))
    spec = importlib.util.spec_from_file_location("rls_primeira_etapa", caminho)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    assert set(modulo.TENANT_DIRETO) == set(r.TENANT_DIRETO)
    assert dict(modulo.DUAS_PARTES) == dict(r.DUAS_PARTES)
    protegidas = set(r.TENANT_DIRETO)
    esperadas = {(e, b.tabela, b.predicado) for e, itens in r.BUSCAS.items() for b in itens if b.tabela in protegidas}
    assert set(modulo.BUSCAS) == esperadas
