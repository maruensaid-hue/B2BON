import zipfile
from datetime import UTC, datetime
from pathlib import Path

import httpx

# Layout público de dados abertos de CNPJ da Receita Federal: pasta datada
# (AAAA-MM, publicada mensalmente, com atraso de alguns dias) contendo até
# 10 arquivos por tipo (Empresas0..9.zip, Estabelecimentos0..9.zip,
# Socios0..9.zip) — nunca um arquivo único.
URL_BASE = "https://dadosabertos.rfb.gov.br/CNPJ/dados_abertos_cnpj"
_QUANTIDADE_SHARDS = 10
_MESES_DE_TOLERANCIA = 3


class MesCompetenciaIndisponivel(RuntimeError):
    """Nenhum mês dos últimos `_MESES_DE_TOLERANCIA` tem dados publicados —
    ou a Receita Federal está atrasada além do normal, ou o layout/domínio
    mudou (precisa investigação manual, não adianta tentar de novo sozinho)."""


def _meses_candidatos(a_partir_de: datetime) -> list[str]:
    """Mês atual primeiro, recuando até `_MESES_DE_TOLERANCIA` meses — a
    RFB publica o snapshot do mês com alguns dias de atraso, então no
    início do mês o mais recente disponível ainda é o anterior."""
    meses = []
    ano, mes = a_partir_de.year, a_partir_de.month
    for _ in range(_MESES_DE_TOLERANCIA + 1):
        meses.append(f"{ano:04d}-{mes:02d}")
        mes -= 1
        if mes == 0:
            mes = 12
            ano -= 1
    return meses


def resolver_mes_competencia() -> str:
    """Primeiro mês (mais recente primeiro) com `Estabelecimentos0.zip`
    publicado — usado como sonda porque estabelecimentos é sempre o
    primeiro tipo publicado dos três num dado mês."""
    for mes in _meses_candidatos(datetime.now(UTC)):
        url = f"{URL_BASE}/{mes}/Estabelecimentos0.zip"
        resposta = httpx.head(url, timeout=30.0, follow_redirects=True)
        if resposta.status_code == 200:
            return mes
    raise MesCompetenciaIndisponivel(
        f"Nenhum mês de competência disponível em {URL_BASE} nos últimos "
        f"{_MESES_DE_TOLERANCIA + 1} meses — verificar manualmente se a Receita "
        "Federal mudou o layout/domínio de publicação."
    )


def _baixar_arquivo(url: str, destino: Path) -> bool:
    """Streama a resposta direto pro disco (nunca materializa o zip inteiro
    em memória — os shards têm centenas de MB cada). Devolve False (sem
    levantar exceção) num 404: shards nem sempre são contíguos/completos
    até o índice 9 em todo mês, e um shard faltando não deve abortar os
    outros nove."""
    with httpx.stream("GET", url, timeout=120.0, follow_redirects=True) as resposta:
        if resposta.status_code == 404:
            return False
        resposta.raise_for_status()
        with open(destino, "wb") as arquivo:
            for pedaco in resposta.iter_bytes():
                arquivo.write(pedaco)
    return True


def _extrair_csv_do_zip(caminho_zip: Path, diretorio_destino: Path) -> str:
    """Cada zip público da RFB contém um único CSV — extrai e devolve o
    caminho, sem manter o zip por perto depois (a chamadora limpa o
    diretório temporário inteiro ao final)."""
    with zipfile.ZipFile(caminho_zip) as arquivo_zip:
        (nome_membro,) = arquivo_zip.namelist()
        arquivo_zip.extract(nome_membro, path=diretorio_destino)
        return str(diretorio_destino / nome_membro)


def baixar_shards(mes: str, tipo: str, diretorio: Path) -> list[str]:
    """Baixa e extrai todos os shards `{tipo}{0..9}.zip` publicados pra um
    mês de competência (`tipo` é "Empresas", "Estabelecimentos" ou
    "Socios"), devolvendo os caminhos dos CSVs extraídos prontos pra
    `receita_federal_loader.carregar_recorte`. Shard individual ausente
    (404) é pulado, não aborta os demais — o layout público às vezes tem
    menos de 10 partes num mês."""
    caminhos_csv: list[str] = []
    for indice in range(_QUANTIDADE_SHARDS):
        url = f"{URL_BASE}/{mes}/{tipo}{indice}.zip"
        caminho_zip = diretorio / f"{tipo}{indice}.zip"
        if not _baixar_arquivo(url, caminho_zip):
            continue
        caminhos_csv.append(_extrair_csv_do_zip(caminho_zip, diretorio))
        caminho_zip.unlink()
    return caminhos_csv
