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


def _linhas(caminhos: str | list[str]):
    """Streama o(s) CSV(s) linha a linha em vez de materializar o arquivo
    inteiro em memória — os arquivos públicos de CNPJ da Receita Federal
    chegam a dezenas de GB (base nacional completa); carregar tudo de uma
    vez antes de filtrar esgota a memória da máquina (ou trava por
    minutos/horas fazendo swap) mesmo quando o recorte final é pequeno.

    Aceita um único caminho (uso manual/script, layout antigo de arquivo
    único) ou uma lista de caminhos (layout público atual da Receita
    Federal, particionado em até 10 arquivos por tipo —
    `receita_federal_downloader`), encadeados como se fosse um só CSV."""
    lista_caminhos = [caminhos] if isinstance(caminhos, str) else caminhos
    for caminho in lista_caminhos:
        with open(caminho, encoding="latin-1", newline="") as arquivo:
            yield from csv.reader(arquivo, delimiter=";")


def _em_lotes(itens, tamanho: int = 500):
    """SQLite tem um limite de parâmetros por consulta (historicamente
    999) — um `IN (...)` com dezenas de milhares de valores de uma vez
    estoura esse limite; lotes menores evitam isso em qualquer versão."""
    lista = list(itens)
    for inicio in range(0, len(lista), tamanho):
        yield lista[inicio : inicio + tamanho]


def _buscar_existentes_em_lotes(db: Session, cnpjs: set[str]) -> dict[str, CnpjEstabelecimento]:
    """Um `IN (...)` em lotes em vez de um `SELECT` por CNPJ — com um
    recorte de dezenas de milhares de linhas, uma consulta ORM por linha
    custa minutos de overhead de rede/ORM mesmo com índice."""
    existentes: dict[str, CnpjEstabelecimento] = {}
    for lote in _em_lotes(cnpjs):
        for estabelecimento in db.query(CnpjEstabelecimento).filter(CnpjEstabelecimento.cnpj.in_(lote)).all():
            existentes[estabelecimento.cnpj] = estabelecimento
    return existentes


def _buscar_socios_existentes_em_lotes(db: Session, cnpjs_basicos: set[str]) -> set[tuple[str, str, str]]:
    existentes: set[tuple[str, str, str]] = set()
    for lote in _em_lotes(cnpjs_basicos):
        for socio in db.query(CnpjSocio).filter(CnpjSocio.cnpj_basico.in_(lote)).all():
            existentes.add((socio.cnpj_basico, socio.nome_socio, socio.qualificacao))
    return existentes


def carregar_recorte(
    db: Session,
    cnae_codigos: list[str],
    ufs: list[str],
    caminho_empresas: str | list[str],
    caminho_estabelecimentos: str | list[str],
    caminho_socios: str | list[str],
) -> int:
    """Carrega no staging local só o recorte de CNAE+UF exigido pelos ICPs
    ativos — nunca a base pública completa (Seção 11 da especificação).

    Espera o layout público de dados abertos da Receita Federal: arquivos
    `;`-delimitados, codificação latin-1, sem cabeçalho. Cada `caminho_*`
    aceita um único arquivo ou uma lista (o layout público atual vem
    particionado em até 10 arquivos por tipo — ver
    `receita_federal_downloader.baixar_shards`). Imprime progresso a cada
    etapa — os arquivos nacionais têm dezenas de milhões de linhas e a
    carga real leva minutos, sem isso parece travado (nenhuma saída até o
    fim).
    """
    cnae_set = set(cnae_codigos)
    uf_set = {uf.upper() for uf in ufs}

    print("Filtrando estabelecimentos por CNAE/UF (arquivo maior, mais demorado)...", flush=True)
    estabelecimentos_no_recorte = []
    for indice, linha in enumerate(_linhas(caminho_estabelecimentos), start=1):
        if linha[11] in cnae_set and linha[19].upper() in uf_set:
            estabelecimentos_no_recorte.append(linha)
        if indice % 5_000_000 == 0:
            print(f"  {indice:,} linha(s) varrida(s), {len(estabelecimentos_no_recorte)} no recorte...", flush=True)
    cnpjs_basicos_no_recorte = {linha[0] for linha in estabelecimentos_no_recorte}
    print(f"{len(estabelecimentos_no_recorte)} estabelecimento(s) no recorte.", flush=True)

    print("Buscando dados de empresas do recorte...", flush=True)
    empresas_por_cnpj_basico = {
        linha[0]: linha for linha in _linhas(caminho_empresas) if linha[0] in cnpjs_basicos_no_recorte
    }

    print("Verificando o que já existe no staging local...", flush=True)
    cnpjs_no_recorte = {f"{linha[0]}{linha[1]}{linha[2]}" for linha in estabelecimentos_no_recorte}
    existentes_por_cnpj = _buscar_existentes_em_lotes(db, cnpjs_no_recorte)

    agora = datetime.now(UTC)
    carregados = 0
    total = len(estabelecimentos_no_recorte)

    print("Gravando estabelecimentos...", flush=True)
    for indice, linha in enumerate(estabelecimentos_no_recorte, start=1):
        cnpj_basico, cnpj_ordem, cnpj_dv = linha[0], linha[1], linha[2]
        empresa = empresas_por_cnpj_basico.get(cnpj_basico)
        if empresa is None:
            continue

        cnpj = f"{cnpj_basico}{cnpj_ordem}{cnpj_dv}"
        capital_social_bruto = empresa[4].replace(",", ".") if empresa[4] else None

        existente = existentes_por_cnpj.get(cnpj)
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

        if indice % 20_000 == 0:
            print(f"  {indice}/{total} gravado(s)...", flush=True)

    print("Vinculando sócios do recorte...", flush=True)
    socios_existentes = _buscar_socios_existentes_em_lotes(db, cnpjs_basicos_no_recorte)

    for linha in _linhas(caminho_socios):
        cnpj_basico = linha[0]
        if cnpj_basico not in cnpjs_basicos_no_recorte:
            continue

        chave = (cnpj_basico, linha[2], linha[4])
        if chave in socios_existentes:
            continue
        socios_existentes.add(chave)

        db.add(
            CnpjSocio(
                cnpj_basico=cnpj_basico,
                nome_socio=linha[2],
                qualificacao=linha[4],
                carregado_em=agora,
            )
        )

    print("Salvando no banco (pode levar alguns segundos)...", flush=True)
    db.commit()
    print("Concluído.", flush=True)
    return carregados
