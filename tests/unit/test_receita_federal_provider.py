from app.providers.account_data.base import FiltroBusca
from app.providers.account_data.receita_federal import ReceitaFederalCNPJProvider
from app.providers.account_data.receita_federal_models import CnpjEstabelecimento


def test_buscar_candidatos_casa_filtro_com_cnae_pontuado(db_session):
    """Bug real (raio-X 2026-08-27): `POST /icp/{id}/contas/gerar` (o botão
    "Gerar lista" na UI) filtra pelo CNAE exatamente como o ICP guardou —
    se o ICP tem o formato humano pontuado e o staging local guarda o
    formato puro-dígitos da Receita Federal, a busca nunca casava nada."""
    db_session.add(
        CnpjEstabelecimento(
            cnpj="12345678000199",
            razao_social="Alpha Tecnologia Ltda",
            cnae_principal="6201500",
            uf="SP",
            situacao_cadastral="ATIVA",
        )
    )
    db_session.commit()

    provider = ReceitaFederalCNPJProvider(db_session)
    candidatos = provider.buscar_candidatos(
        FiltroBusca(cnae_codigos=["6201-5/00"], ufs=["sp"], limite=10)
    )

    assert len(candidatos) == 1
    assert candidatos[0].cnpj == "12345678000199"
