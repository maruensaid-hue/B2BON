"""O registro de RLS (D-110, D-111) classifica TODA tabela do modelo. Tabela nova sem classificação quebra este teste: ou ganha política (e migração), ou entra em PENDENTES/GLOBAIS com o motivo."""

import importlib.util
from pathlib import Path

import app.main  # noqa: F401 — registra também as tabelas que só o app importa (webhooks de parceiro, relatório)
import app.models  # noqa: F401
from app.db import rls_registro as r
from app.db import rls_sql
from app.db.base import Base

RAIZ = Path(__file__).resolve().parents[2]


def _tem_tenant(tabela) -> bool:
    return any(c == "tenant_id" or c.startswith("tenant_id_") for c in tabela.columns.keys())


def _grupos() -> dict[str, set[str]]:
    return {
        "TENANT_DIRETO": set(r.TENANT_DIRETO),
        "TENANT_NULAVEL_ETAPA2": set(r.TENANT_NULAVEL_ETAPA2),
        "TENANT_COLUNA_ETAPA2": set(r.TENANT_COLUNA_ETAPA2),
        "DUAS_PARTES": set(r.DUAS_PARTES),
        "LEITURA_COMPARTILHADA": set(r.LEITURA_COMPARTILHADA),
        "HERDADAS": set(r.HERDADAS),
        "PENDENTES": set(r.PENDENTES),
        "GLOBAIS": set(r.GLOBAIS),
    }


def _carregar_migracao(prefixo: str):
    caminho = next((RAIZ / "alembic" / "versions").glob(f"{prefixo}_*.py"))
    spec = importlib.util.spec_from_file_location(f"migracao_{prefixo}", caminho)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


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
    for tabela in r.TENANT_NULAVEL_ETAPA2:
        assert "tenant_id" in Base.metadata.tables[tabela].columns, tabela
    for tabela, coluna in r.TENANT_COLUNA_ETAPA2.items():
        assert coluna in Base.metadata.tables[tabela].columns, tabela
    for tabela, colunas in r.DUAS_PARTES.items():
        assert all(c in Base.metadata.tables[tabela].columns for c in colunas)
    funcoes_do_pai = set(rls_sql.FUNCOES_DO_PAI) | {n.split("(")[0] for n in rls_sql.NOMES_FUNCOES_ETAPA2}
    for tabela, (coluna_fk, funcao, _compartilhada) in r.HERDADAS.items():
        assert coluna_fk in Base.metadata.tables[tabela].columns, tabela
        assert funcao in funcoes_do_pai, f"{tabela}: função {funcao} não existe nas funções de RLS"


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
    for tabela, politicas in r.POLITICAS_ESPECIAIS_ETAPA2.items():
        assert tabela in existentes, tabela
        for _nome, comando, usando, verificando in politicas:
            assert comando in {"ALL", "SELECT", "INSERT", "UPDATE", "DELETE"}
            assert (usando is not None) or (verificando is not None)


def test_politicas_avulsas_so_em_tabelas_protegidas_pela_segunda_etapa():
    protegidas = (
        set(r.TENANT_DIRETO_ETAPA2) | set(r.TENANT_NULAVEL_ETAPA2) | set(r.TENANT_COLUNA_ETAPA2) | set(r.DUAS_PARTES_ETAPA2) | set(r.LEITURA_COMPARTILHADA_ETAPA2) | set(r.HERDADAS_ETAPA2)
    )
    assert set(r.POLITICAS_ESPECIAIS_ETAPA2) <= protegidas


def test_migracao_da_primeira_etapa_congelou_o_que_era_o_registro_dela():
    """A migração tem cópia das listas; se alguém mexer num lado só, este teste acusa (tabela nova entra em migração nova, não editando esta)."""
    modulo = _carregar_migracao("e7a9c1d3f5b8")
    assert set(modulo.TENANT_DIRETO) == set(r.TENANT_DIRETO_ETAPA1)
    assert dict(modulo.DUAS_PARTES) == dict(r.DUAS_PARTES_ETAPA1)
    protegidas = set(r.TENANT_DIRETO_ETAPA1)
    esperadas = {(e, b.tabela, b.predicado) for e, itens in r.BUSCAS.items() for b in itens if b.tabela in protegidas}
    assert set(modulo.BUSCAS) == esperadas


def test_migracao_da_segunda_etapa_congelou_o_registro_dela():
    modulo = _carregar_migracao("a3c5e7b9d1f2")
    assert set(modulo.ETAPA1) == set(r.TENANT_DIRETO_ETAPA1) | set(r.DUAS_PARTES_ETAPA1)
    assert set(modulo.TENANT_DIRETO) == set(r.TENANT_DIRETO_ETAPA2)
    assert set(modulo.TENANT_NULAVEL) == set(r.TENANT_NULAVEL_ETAPA2)
    assert dict(modulo.TENANT_COLUNA) == dict(r.TENANT_COLUNA_ETAPA2)
    assert dict(modulo.DUAS_PARTES) == dict(r.DUAS_PARTES_ETAPA2)
    assert set(modulo.LEITURA_COMPARTILHADA) == set(r.LEITURA_COMPARTILHADA_ETAPA2)
    assert {k: tuple(v) for k, v in modulo.HERDADAS.items()} == dict(r.HERDADAS_ETAPA2)
    esperadas_politicas = {(t, *p) for t, itens in r.POLITICAS_ESPECIAIS_ETAPA2.items() for p in itens}
    assert {tuple(p) for p in modulo.POLITICAS_ESPECIAIS} == esperadas_politicas
    novas = set(modulo._tabelas_novas())
    esperadas_buscas = {(e, b.tabela, b.predicado) for e, itens in r.BUSCAS.items() for b in itens if b.tabela in novas}
    assert {tuple(b) for b in modulo.BUSCAS} == esperadas_buscas


def test_tabelas_com_tenant_nulo_sao_exatamente_as_declaradas():
    """Só `tenant_id` nulo justifica ficar fora de TENANT_DIRETO (a política por tenant não enxerga linha sem dono)."""
    nulaveis = {
        n for n, t in Base.metadata.tables.items() if "tenant_id" in t.columns and t.columns["tenant_id"].nullable and n in (set(r.TENANT_DIRETO) | set(r.TENANT_NULAVEL_ETAPA2))
    }
    assert nulaveis == set(r.TENANT_NULAVEL_ETAPA2)
