from sqlalchemy.orm import Session

from app.providers.account_data.base import (
    AccountDataProvider,
    ContaCandidata,
    DecisorCandidato,
    FiltroBusca,
)
from app.providers.account_data.receita_federal_models import CnpjEstabelecimento, CnpjSocio


class ReceitaFederalCNPJProvider(AccountDataProvider):
    """Adaptador primário do MVP: base pública de CNPJ (dados abertos da
    Receita Federal), restrito ao recorte já carregado via
    `receita_federal_loader.carregar_recorte` — nunca a base completa.
    """

    def __init__(self, db: Session) -> None:
        self._db = db

    def buscar_candidatos(self, filtro: FiltroBusca) -> list[ContaCandidata]:
        query = self._db.query(CnpjEstabelecimento).filter(
            CnpjEstabelecimento.cnae_principal.in_(filtro.cnae_codigos),
            CnpjEstabelecimento.uf.in_([uf.upper() for uf in filtro.ufs]),
            CnpjEstabelecimento.situacao_cadastral == filtro.situacao_cadastral,
        )
        if filtro.porte:
            query = query.filter(CnpjEstabelecimento.porte == filtro.porte)

        registros = query.limit(filtro.limite).all()
        return [
            ContaCandidata(
                cnpj=registro.cnpj,
                razao_social=registro.razao_social,
                nome_fantasia=registro.nome_fantasia,
                cnae_principal=registro.cnae_principal,
                porte=registro.porte,
                capital_social=registro.capital_social,
                uf=registro.uf,
                municipio=registro.municipio,
                situacao_cadastral=registro.situacao_cadastral,
                data_abertura=registro.data_abertura,
            )
            for registro in registros
        ]

    def buscar_decisores(self, cnpj: str) -> list[DecisorCandidato]:
        cnpj_basico = cnpj[:8]
        registros = self._db.query(CnpjSocio).filter_by(cnpj_basico=cnpj_basico).all()
        return [
            DecisorCandidato(cnpj=cnpj, nome=registro.nome_socio, qualificacao=registro.qualificacao)
            for registro in registros
        ]
