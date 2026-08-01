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
