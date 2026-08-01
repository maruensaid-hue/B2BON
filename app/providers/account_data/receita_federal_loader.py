import csv
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.providers.account_data.receita_federal_models import CnpjEstabelecimento, CnpjSocio

# Códigos do layout público de dados abertos de CNPJ da Receita Federal.
_SITUACAO_CADASTRAL = {
    "01": "NULA",
    "02": "ATIVA",
    "03": "SUSPENSA",
    "04": "INAPTA",
    "08": "BAIXADA",
}

_PORTE_EMPRESA = {
    "00": None,
    "01": "MICRO",
    "03": "PEQUENO",
    "05": "DEMAIS",
}


def _ler_csv(caminho: str) -> list[list[str]]:
    with open(caminho, encoding="latin-1", newline="") as arquivo:
        return list(csv.reader(arquivo, delimiter=";"))


def carregar_recorte(
    db: Session,
    cnae_codigos: list[str],
    ufs: list[str],
    caminho_empresas: str,
    caminho_estabelecimentos: str,
    caminho_socios: str,
) -> int:
    """Carrega no staging local só o recorte de CNAE+UF exigido pelos ICPs
    ativos — nunca a base pública completa (Seção 11 da especificação).

    Espera o layout público de dados abertos da Receita Federal: arquivos
    `;`-delimitados, codificação latin-1, sem cabeçalho.
    """
    cnae_set = set(cnae_codigos)
    uf_set = {uf.upper() for uf in ufs}

    empresas_por_cnpj_basico = {linha[0]: linha for linha in _ler_csv(caminho_empresas)}

    estabelecimentos_no_recorte = [
        linha
        for linha in _ler_csv(caminho_estabelecimentos)
        if linha[11] in cnae_set and linha[19].upper() in uf_set
    ]

    agora = datetime.now(UTC)
    carregados = 0

    for linha in estabelecimentos_no_recorte:
        cnpj_basico, cnpj_ordem, cnpj_dv = linha[0], linha[1], linha[2]
        empresa = empresas_por_cnpj_basico.get(cnpj_basico)
        if empresa is None:
            continue

        cnpj = f"{cnpj_basico}{cnpj_ordem}{cnpj_dv}"
        capital_social_bruto = empresa[4].replace(",", ".") if empresa[4] else None

        existente = db.query(CnpjEstabelecimento).filter_by(cnpj=cnpj).one_or_none()
        estabelecimento = existente or CnpjEstabelecimento(cnpj=cnpj)
        estabelecimento.razao_social = empresa[1]
        estabelecimento.nome_fantasia = linha[4] or None
        estabelecimento.cnae_principal = linha[11]
        estabelecimento.porte = _PORTE_EMPRESA.get(empresa[5], empresa[5])
        estabelecimento.capital_social = float(capital_social_bruto) if capital_social_bruto else None
        estabelecimento.uf = linha[19].upper()
        estabelecimento.municipio = linha[20] or None
        estabelecimento.situacao_cadastral = _SITUACAO_CADASTRAL.get(linha[5], linha[5])
        estabelecimento.data_abertura = linha[10] or None
        estabelecimento.carregado_em = agora

        if existente is None:
            db.add(estabelecimento)
        carregados += 1

    cnpjs_basicos_no_recorte = {linha[0] for linha in estabelecimentos_no_recorte}

    for linha in _ler_csv(caminho_socios):
        cnpj_basico = linha[0]
        if cnpj_basico not in cnpjs_basicos_no_recorte:
            continue

        db.add(
            CnpjSocio(
                cnpj_basico=cnpj_basico,
                nome_socio=linha[2],
                qualificacao=linha[4],
                carregado_em=agora,
            )
        )

    db.commit()
    return carregados
