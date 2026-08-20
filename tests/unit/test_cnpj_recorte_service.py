from pathlib import Path

import pytest

from app.models.icp import ICP
from app.models.recorte_cnpj_estado import RecorteCnpjEstado
from app.providers.account_data.receita_federal_models import CnpjEstabelecimento
from app.services import cnpj_recorte_service

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "receita_federal"


def _criar_icp(db_session, tenant_id: str, ativo: bool, cnae_codigos: list[str], ufs: list[str]) -> ICP:
    icp = ICP(
        tenant_id=tenant_id,
        grupo_id=f"grupo-{tenant_id}",
        nome="ICP Teste",
        ativo=ativo,
        segmento="Tecnologia",
        porte="PEQUENO",
        regiao="SP",
        cnae_codigos=cnae_codigos,
        ufs=ufs,
    )
    db_session.add(icp)
    db_session.commit()
    return icp


def test_uniao_cnae_uf_cobre_todos_os_tenants_sem_duplicatas(db_session):
    _criar_icp(db_session, "tenant-a", ativo=True, cnae_codigos=["6201500"], ufs=["SP"])
    _criar_icp(db_session, "tenant-b", ativo=True, cnae_codigos=["6201500", "4711301"], ufs=["RJ"])
    _criar_icp(db_session, "tenant-c", ativo=False, cnae_codigos=["9999999"], ufs=["AM"])

    cnae_codigos, ufs = cnpj_recorte_service.uniao_cnae_uf_ativos_todos_tenants(db_session)

    assert cnae_codigos == ["4711301", "6201500"]
    assert ufs == ["RJ", "SP"]


def test_sem_nenhum_icp_ativo_nao_executa(db_session):
    resultado = cnpj_recorte_service.atualizar_recorte_automatico(db_session)

    assert resultado == {"executado": False, "motivo": "nenhum ICP ativo em nenhum tenant"}


def _mockar_download(monkeypatch: pytest.MonkeyPatch, mes: str = "2026-01") -> None:
    monkeypatch.setattr(cnpj_recorte_service, "resolver_mes_competencia", lambda: mes)

    def _baixar_shards_falso(mes_recebido: str, tipo: str, diretorio) -> list[str]:
        nome = {"Empresas": "empresas.csv", "Estabelecimentos": "estabelecimentos.csv", "Socios": "socios.csv"}[tipo]
        return [str(FIXTURES / nome)]

    monkeypatch.setattr(cnpj_recorte_service, "baixar_shards", _baixar_shards_falso)


def test_primeira_execucao_baixa_e_carrega_o_recorte(db_session, monkeypatch: pytest.MonkeyPatch):
    _criar_icp(db_session, "tenant-a", ativo=True, cnae_codigos=["6201500"], ufs=["SP"])
    _mockar_download(monkeypatch)

    resultado = cnpj_recorte_service.atualizar_recorte_automatico(db_session)

    assert resultado["executado"] is True
    assert resultado["mes_competencia"] == "2026-01"
    assert resultado["estabelecimentos_carregados"] == 2  # Alpha e Gama (fixture existente)

    estado = db_session.query(RecorteCnpjEstado).one()
    assert estado.mes_competencia == "2026-01"
    assert estado.cnae_codigos_cobertos == ["6201500"]
    assert estado.ufs_cobertos == ["SP"]
    assert db_session.query(CnpjEstabelecimento).count() == 2


def test_segunda_execucao_sem_icp_novo_nao_baixa_de_novo(db_session, monkeypatch: pytest.MonkeyPatch):
    _criar_icp(db_session, "tenant-a", ativo=True, cnae_codigos=["6201500"], ufs=["SP"])
    _mockar_download(monkeypatch)
    cnpj_recorte_service.atualizar_recorte_automatico(db_session)

    chamadas = []
    monkeypatch.setattr(
        cnpj_recorte_service,
        "baixar_shards",
        lambda mes, tipo, diretorio: chamadas.append(tipo) or [],
    )

    resultado = cnpj_recorte_service.atualizar_recorte_automatico(db_session)

    assert resultado["executado"] is False
    assert chamadas == []  # nao baixou nada de novo


def test_icp_novo_com_cnae_diferente_dispara_novo_download(db_session, monkeypatch: pytest.MonkeyPatch):
    _criar_icp(db_session, "tenant-a", ativo=True, cnae_codigos=["6201500"], ufs=["SP"])
    _mockar_download(monkeypatch)
    cnpj_recorte_service.atualizar_recorte_automatico(db_session)

    # ICP novo com UF ainda nao coberta
    _criar_icp(db_session, "tenant-b", ativo=True, cnae_codigos=["6201500"], ufs=["RJ"])

    tipos_baixados = []
    monkeypatch.setattr(
        cnpj_recorte_service,
        "baixar_shards",
        lambda mes, tipo, diretorio: tipos_baixados.append(tipo)
        or [str(FIXTURES / {"Empresas": "empresas.csv", "Estabelecimentos": "estabelecimentos.csv", "Socios": "socios.csv"}[tipo])],
    )

    resultado = cnpj_recorte_service.atualizar_recorte_automatico(db_session)

    assert resultado["executado"] is True
    assert set(tipos_baixados) == {"Empresas", "Estabelecimentos", "Socios"}
    estado = db_session.query(RecorteCnpjEstado).one()
    assert estado.ufs_cobertos == ["RJ", "SP"]
