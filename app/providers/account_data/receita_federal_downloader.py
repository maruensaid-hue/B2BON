import re
import unicodedata
import zipfile
from pathlib import Path

import httpx

# O domínio oficial original (dadosabertos.rfb.gov.br) saiu do ar (raio-X
# 2026-08-26: `httpx.ConnectTimeout` em produção E também não abre no
# navegador comum do usuário — não é bloqueio de IP de nuvem, o domínio
# mudou/saiu do ar de verdade). Usamos o espelho da Casa dos Dados
# (CDN Cloudflare, atualizado mensalmente, mesmo layout de shards:
# Empresas0..9.zip, Estabelecimentos0..9.zip, Socios0..9.zip) — fonte
# declarada pelo próprio espelho: https://arquivos.receitafederal.gov.br
# (novo endereço oficial, mas atrás de um compartilhamento tipo Nextcloud,
# sem listagem simples de pastas como o layout antigo tinha).
URL_BASE = "https://dados-abertos-rf-cnpj.casadosdados.com.br/arquivos"
_QUANTIDADE_SHARDS = 10
_PADRAO_PASTA_DATA = re.compile(r'href="(\d{4}-\d{2}-\d{2})/"')
_NAO_DIGITO = re.compile(r"\D")


def normalizar_cnae(codigo: str) -> str:
    """A RFB grava CNAE como string de dígitos puros (ex.: "6201501") no
    arquivo público — mas é comum guardar/digitar o formato humano
    pontuado (ex.: "6201-5/01", como aparece nas tabelas oficiais de
    consulta). Sem normalizar os dois lados pro mesmo formato antes de
    comparar, a busca nunca casa nada (raio-X 2026-08-27: 70 milhões de
    linhas varridas na carga inicial, 0 no recorte — o ICP do usuário
    tinha o CNAE pontuado)."""
    return _NAO_DIGITO.sub("", codigo)


_UFS_VALIDAS = {
    "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS",
    "MG", "PA", "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC",
    "SP", "SE", "TO",
}

_NOME_ESTADO_PARA_UF = {
    "ACRE": "AC", "ALAGOAS": "AL", "AMAPA": "AP", "AMAZONAS": "AM", "BAHIA": "BA",
    "CEARA": "CE", "DISTRITO FEDERAL": "DF", "ESPIRITO SANTO": "ES", "GOIAS": "GO",
    "MARANHAO": "MA", "MATO GROSSO": "MT", "MATO GROSSO DO SUL": "MS",
    "MINAS GERAIS": "MG", "PARA": "PA", "PARAIBA": "PB", "PARANA": "PR",
    "PERNAMBUCO": "PE", "PIAUI": "PI", "RIO DE JANEIRO": "RJ",
    "RIO GRANDE DO NORTE": "RN", "RIO GRANDE DO SUL": "RS", "RONDONIA": "RO",
    "RORAIMA": "RR", "SANTA CATARINA": "SC", "SAO PAULO": "SP", "SERGIPE": "SE",
    "TOCANTINS": "TO",
}


def normalizar_uf(uf: str) -> str:
    """A RFB grava UF sempre como sigla de 2 letras (ex.: "SP") no arquivo
    público, mas o campo de UFs do ICP no frontend é texto livre separado
    por vírgula, sem exemplo nem validação — nada impede a pessoa de
    digitar o nome completo do estado ("São Paulo") ou uma sigla em caixa
    baixa. Sem normalizar pro mesmo formato da Receita Federal antes de
    comparar, a busca nunca casa nada — mesma classe de bug do CNAE
    pontuado acima, só que na UF: `gerar_lista` volta vazio sem erro
    nenhum pra avisar. Permissivo (igual `normalizar_cnae`): um valor não
    reconhecido passa adiante só em caixa alta/sem espaço, em vez de
    travar o cadastro do ICP."""
    texto = "".join(c for c in unicodedata.normalize("NFKD", uf.strip().upper()) if not unicodedata.combining(c))
    if texto in _UFS_VALIDAS:
        return texto
    return _NOME_ESTADO_PARA_UF.get(texto, texto)


class MesCompetenciaIndisponivel(RuntimeError):
    """Nenhuma pasta de competência encontrada no índice do espelho — ou a
    Receita Federal/o espelho está fora do ar, ou o layout/domínio mudou de
    novo (precisa investigação manual, não adianta tentar de novo sozinho)."""


def resolver_mes_competencia() -> str:
    """Pasta mais recente publicada pelo espelho — formato "AAAA-MM-DD"
    (dia exato da publicação, não necessariamente o dia 1; a RFB publica em
    datas variáveis a cada mês). Lê o índice (listagem HTML padrão de
    servidor de arquivos) em vez de tentar adivinhar/sondar datas, porque
    não há padrão fixo de dia de publicação."""
    resposta = httpx.get(f"{URL_BASE}/", timeout=30.0, follow_redirects=True)
    resposta.raise_for_status()
    pastas = _PADRAO_PASTA_DATA.findall(resposta.text)
    if not pastas:
        raise MesCompetenciaIndisponivel(
            f"Nenhuma pasta de competência encontrada em {URL_BASE} — verificar "
            "manualmente se o espelho mudou de layout/domínio."
        )
    return max(pastas)


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
