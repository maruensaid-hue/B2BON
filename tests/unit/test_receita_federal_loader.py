from pathlib import Path

from app.providers.account_data.base import FiltroBusca
from app.providers.account_data.receita_federal import ReceitaFederalCNPJProvider
from app.providers.account_data.receita_federal_loader import carregar_recorte
from app.providers.account_data.receita_federal_models import CnpjEstabelecimento

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "receita_federal"


def _carregar(db_session) -> int:
    return carregar_recorte(
        db_session,
        cnae_codigos=["6201500"],
        ufs=["SP"],
        caminho_empresas=str(FIXTURES / "empresas.csv"),
        caminho_estabelecimentos=str(FIXTURES / "estabelecimentos.csv"),
        caminho_socios=str(FIXTURES / "socios.csv"),
    )


def test_carrega_apenas_o_recorte_de_cnae_e_uf(db_session):
    """Nunca importa a base completa — só CNAE+UF do recorte pedido."""
    carregados = _carregar(db_session)

    assert carregados == 2  # Alpha e Gama (CNAE+UF batem); Beta (RJ) fica de fora
    cnpjs = {e.cnpj for e in db_session.query(CnpjEstabelecimento).all()}
    assert "44555666000150" not in cnpjs  # Beta nunca entra no staging


def test_provider_retorna_apenas_situacao_ativa_por_padrao(db_session):
    _carregar(db_session)
    provider = ReceitaFederalCNPJProvider(db_session)

    candidatos = provider.buscar_candidatos(FiltroBusca(cnae_codigos=["6201500"], ufs=["SP"], limite=10))

    nomes = {c.razao_social for c in candidatos}
    assert nomes == {"EMPRESA ALPHA LTDA"}  # Gama está SUSPENSA, não entra


def test_provider_calcula_campos_a_partir_do_layout_publico(db_session):
    _carregar(db_session)
    provider = ReceitaFederalCNPJProvider(db_session)

    candidatos = provider.buscar_candidatos(FiltroBusca(cnae_codigos=["6201500"], ufs=["SP"], limite=10))
    alpha = candidatos[0]

    assert alpha.cnpj == "11222333000191"
    assert alpha.porte == "MICRO"
    assert alpha.capital_social == 150000.0
    assert alpha.uf == "SP"
    assert alpha.situacao_cadastral == "ATIVA"


def test_buscar_decisores_le_qsa_do_recorte(db_session):
    _carregar(db_session)
    provider = ReceitaFederalCNPJProvider(db_session)

    decisores = provider.buscar_decisores("11222333000191")

    nomes = {d.nome for d in decisores}
    assert nomes == {"JOAO DA SILVA", "MARIA SOUZA"}


def test_carregar_recorte_aceita_lista_de_shards_por_tipo(db_session, tmp_path):
    """Layout público atual da Receita Federal particiona cada tipo em até
    10 arquivos (`receita_federal_downloader.baixar_shards`) — o loader
    precisa encadear todos, não só aceitar um caminho único."""
    estab_shard_0 = tmp_path / "estab0.csv"
    estab_shard_0.write_text(
        "11222333;0001;91;1;ALPHA TECH;02;20200101;00;;;20200101;6201500;;RUA;EXEMPLO;100;;CENTRO;01000000;SP;7107\n",
        encoding="latin-1",
    )
    estab_shard_1 = tmp_path / "estab1.csv"
    estab_shard_1.write_text(
        "77888999;0001;30;1;GAMA TEC;02;20220101;00;;;20220101;6201500;;RUA;TERCEIRA;300;;CENTRO;01000001;SP;7107\n",
        encoding="latin-1",
    )
    empresas_shard_0 = tmp_path / "emp0.csv"
    empresas_shard_0.write_text("11222333;EMPRESA ALPHA LTDA;2062;49;150000,00;01;\n", encoding="latin-1")
    empresas_shard_1 = tmp_path / "emp1.csv"
    empresas_shard_1.write_text("77888999;EMPRESA GAMA LTDA;2062;49;50000,00;01;\n", encoding="latin-1")
    socios_shard = tmp_path / "socios0.csv"
    socios_shard.write_text("11222333;2;JOAO DA SILVA;***123456**;49;20200101;;;;;5\n", encoding="latin-1")

    carregados = carregar_recorte(
        db_session,
        cnae_codigos=["6201500"],
        ufs=["SP"],
        caminho_empresas=[str(empresas_shard_0), str(empresas_shard_1)],
        caminho_estabelecimentos=[str(estab_shard_0), str(estab_shard_1)],
        caminho_socios=[str(socios_shard)],
    )

    assert carregados == 2
    cnpjs = {e.cnpj for e in db_session.query(CnpjEstabelecimento).all()}
    assert cnpjs == {"11222333000191", "77888999000130"}
