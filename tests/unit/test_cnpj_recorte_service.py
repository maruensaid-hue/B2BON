from pathlib import Path

import pytest

from app.models.icp import ICP
from app.models.recorte_cnpj_estado import RecorteCnpjEstado
from app.providers.account_data.receita_federal_models import CnpjEstabelecimento, CnpjSocio
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


def test_uniao_cnae_normaliza_formato_pontuado(db_session):
    """Bug real (raio-X 2026-08-27): ICP guardado com CNAE no formato
    humano pontuado (como aparece nas tabelas oficiais de consulta) nunca
    batia com o formato puro-dígitos do CSV da Receita Federal — a
    varredura completa (70 milhões de linhas em produção) sempre dava
    zero resultado, mesmo com o download certo."""
    _criar_icp(db_session, "tenant-a", ativo=True, cnae_codigos=["6201-5/00"], ufs=["SP"])

    cnae_codigos, _ = cnpj_recorte_service.uniao_cnae_uf_ativos_todos_tenants(db_session)

    assert cnae_codigos == ["6201500"]


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


def test_icp_com_cnae_pontuado_carrega_o_recorte_de_ponta_a_ponta(db_session, monkeypatch: pytest.MonkeyPatch):
    _criar_icp(db_session, "tenant-a", ativo=True, cnae_codigos=["6201-5/00"], ufs=["SP"])
    _mockar_download(monkeypatch)

    resultado = cnpj_recorte_service.atualizar_recorte_automatico(db_session)

    assert resultado["executado"] is True
    assert resultado["estabelecimentos_carregados"] == 2
    assert db_session.query(CnpjEstabelecimento).count() == 2


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


def test_icp_novo_nao_reescreve_recorte_ja_coberto(db_session, monkeypatch: pytest.MonkeyPatch):
    """Raio-X 2026-09-11: um ICP novo (de outro tenant) que amplia a
    união de CNAE/UF só precisa carregar a diferença — não pode
    reescrever no banco o que já estava correto, senão um ICP amplo
    (muitas empresas) obriga regravar TODO o recorte de TODOS os ICPs
    ativos a cada atualização."""
    _criar_icp(db_session, "tenant-a", ativo=True, cnae_codigos=["6201500"], ufs=["SP"])
    _mockar_download(monkeypatch)
    cnpj_recorte_service.atualizar_recorte_automatico(db_session)  # Alpha + Gama

    _criar_icp(db_session, "tenant-b", ativo=True, cnae_codigos=["4711301"], ufs=["RJ"])
    _mockar_download(monkeypatch)  # mesmo mês de competência

    resultado = cnpj_recorte_service.atualizar_recorte_automatico(db_session)

    assert resultado["executado"] is True
    assert resultado["estabelecimentos_carregados"] == 1  # só Beta é genuinamente novo
    assert db_session.query(CnpjEstabelecimento).count() == 3


def test_atualizar_recorte_passa_cobertura_antiga_como_exclusao(db_session, monkeypatch: pytest.MonkeyPatch):
    _criar_icp(db_session, "tenant-a", ativo=True, cnae_codigos=["6201500"], ufs=["SP"])
    _mockar_download(monkeypatch)
    cnpj_recorte_service.atualizar_recorte_automatico(db_session)

    _criar_icp(db_session, "tenant-b", ativo=True, cnae_codigos=["4711301"], ufs=["RJ"])
    _mockar_download(monkeypatch)
    capturados = {}

    def _espiao(db, cnae_codigos, ufs, caminho_empresas, caminho_estabelecimentos, caminho_socios, cnae_ja_cobertos=None, ufs_ja_cobertos=None):
        capturados["cnae_ja_cobertos"] = cnae_ja_cobertos
        capturados["ufs_ja_cobertos"] = ufs_ja_cobertos
        return 0

    monkeypatch.setattr(cnpj_recorte_service, "carregar_recorte", _espiao)

    cnpj_recorte_service.atualizar_recorte_automatico(db_session)

    assert capturados["cnae_ja_cobertos"] == {"6201500"}
    assert capturados["ufs_ja_cobertos"] == {"SP"}


def test_mes_competencia_novo_recarrega_tudo_mesmo_ja_coberto(db_session, monkeypatch: pytest.MonkeyPatch):
    """Diferente de um ICP novo: quando a Receita Federal publica um mês
    de competência mais recente, os dados de empresas JÁ cobertas também
    podem ter mudado — não dá pra pular a regravação só porque o CNAE/UF
    já era conhecido."""
    _criar_icp(db_session, "tenant-a", ativo=True, cnae_codigos=["6201500"], ufs=["SP"])
    _mockar_download(monkeypatch, mes="2026-01")
    cnpj_recorte_service.atualizar_recorte_automatico(db_session)

    _mockar_download(monkeypatch, mes="2026-02")
    capturados = {}

    def _espiao(db, cnae_codigos, ufs, caminho_empresas, caminho_estabelecimentos, caminho_socios, cnae_ja_cobertos=None, ufs_ja_cobertos=None):
        capturados["cnae_ja_cobertos"] = cnae_ja_cobertos
        capturados["ufs_ja_cobertos"] = ufs_ja_cobertos
        return 0

    monkeypatch.setattr(cnpj_recorte_service, "carregar_recorte", _espiao)

    resultado = cnpj_recorte_service.atualizar_recorte_automatico(db_session)

    assert resultado["executado"] is True
    assert capturados["cnae_ja_cobertos"] is None
    assert capturados["ufs_ja_cobertos"] is None


def test_poda_remove_apenas_cnae_uf_nao_usados_e_encolhe_estado(db_session, monkeypatch: pytest.MonkeyPatch):
    _criar_icp(db_session, "tenant-a", ativo=True, cnae_codigos=["6201500"], ufs=["SP"])
    icp_b = _criar_icp(db_session, "tenant-b", ativo=True, cnae_codigos=["4711301"], ufs=["RJ"])
    _mockar_download(monkeypatch)
    cnpj_recorte_service.atualizar_recorte_automatico(db_session)
    assert db_session.query(CnpjEstabelecimento).count() == 3

    # ICP B (única fonte de demanda por cnae=4711301/RJ, o recorte da
    # Beta) foi desativado — ninguém mais precisa desse recorte.
    icp_b.ativo = False
    db_session.commit()

    resultado = cnpj_recorte_service.podar_recorte_nao_utilizado(db_session)

    assert resultado["executado"] is True
    assert resultado["estabelecimentos_removidos"] == 1
    cnpjs_restantes = {e.cnpj for e in db_session.query(CnpjEstabelecimento).all()}
    assert cnpjs_restantes == {"11222333000191", "77888999000130"}
    estado = db_session.query(RecorteCnpjEstado).one()
    assert estado.cnae_codigos_cobertos == ["6201500"]
    assert estado.ufs_cobertos == ["SP"]


def test_poda_remove_socios_orfaos(db_session, monkeypatch: pytest.MonkeyPatch):
    _criar_icp(db_session, "tenant-a", ativo=True, cnae_codigos=["6201500"], ufs=["SP"])
    _mockar_download(monkeypatch)
    cnpj_recorte_service.atualizar_recorte_automatico(db_session)

    db_session.add(CnpjSocio(cnpj_basico="99999999", nome_socio="Sócio Órfão", qualificacao="49"))
    db_session.commit()

    resultado = cnpj_recorte_service.podar_recorte_nao_utilizado(db_session)

    assert resultado["socios_removidos"] == 1
    restantes = {s.cnpj_basico for s in db_session.query(CnpjSocio).all()}
    assert "99999999" not in restantes
    assert "11222333" in restantes  # sócios do Alpha (ainda coberto) continuam


def test_poda_sem_icp_ativo_nao_apaga_nada_por_seguranca(db_session):
    resultado = cnpj_recorte_service.podar_recorte_nao_utilizado(db_session)

    assert resultado == {
        "executado": False,
        "motivo": "nenhum ICP ativo em nenhum tenant — nada podado por segurança",
    }
