"""Leitura de texto de PDF não confiável, em processo filho isolado (V5.2.1, Fase 5).

PDF de terceiros é entrada hostil: arquivo malformado, bomba de descompressão, milhares de páginas, criptografia, conteúdo ativo. Por isso:

- o arquivo só é aceito se **começa como PDF de verdade** (`%PDF-` nos primeiros 1024 bytes) e o leitor consegue abri-lo; extensão e `Content-Type`
  declarados por quem enviou não provam nada;
- a extração roda num **subprocesso** (`python -E -c`) com **timeout** (o processo é morto) e, em POSIX, **limite de memória** (`RLIMIT_AS`); a falha do
  filho nunca derruba a API;
- limites de **páginas**, **caracteres por página** e **caracteres no total**; excedeu → trunca e avisa, ou recusa quando o PDF tem páginas demais;
- PDF criptografado só é lido se abrir com senha vazia; senão é recusado;
- **nada é executado**: o leitor (`pypdf`) só extrai texto. Marcadores de conteúdo ativo (`/JavaScript`, `/JS`, `/Launch`, `/EmbeddedFile`) apenas geram um aviso;
- o texto extraído sai sem caracteres de controle e deve ser tratado como **dado não confiável** por quem o usa (nunca como instrução).

Sem OCR: PDF digitalizado (sem camada de texto) devolve páginas vazias, e quem chama registra "sem texto" em vez de inventar conteúdo."""

import json
import re
import subprocess
import sys
from dataclasses import dataclass, field

TAMANHO_MAXIMO_BYTES = 25 * 1024 * 1024
MAX_PAGINAS = 300
MAX_CHARS_PAGINA = 120_000
MAX_CHARS_TOTAL = 2_500_000
TIMEOUT_SEGUNDOS = 25.0
LIMITE_MEMORIA_BYTES = 1_500_000_000  # só em POSIX (RLIMIT_AS); no Windows de desenvolvimento vale só o timeout
_MARCADORES_ATIVOS = (b"/JavaScript", b"/JS", b"/Launch", b"/EmbeddedFile")
_CONTROLE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


class PdfInvalido(Exception):
    """Recusado, com mensagem segura para mostrar ao usuário (sem caminho, sem detalhe interno)."""


@dataclass
class TextoPdf:
    paginas: list[str]
    total_paginas: int
    truncado: bool = False
    avisos: list[str] = field(default_factory=list)


# Executado em outro processo. Só stdlib + pypdf; lê o PDF do stdin e devolve JSON no stdout.
_TRABALHADOR = r"""
import json, sys
try:
    import resource
    limite = int(sys.argv[4])
    resource.setrlimit(resource.RLIMIT_AS, (limite, limite))
except Exception:
    pass
max_paginas, max_pagina, max_total = int(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3])
dados = sys.stdin.buffer.read()
def sair(**kw):
    sys.stdout.write(json.dumps(kw, ensure_ascii=False)); sys.stdout.flush(); sys.exit(0)
try:
    import io
    from pypdf import PdfReader
    leitor = PdfReader(io.BytesIO(dados))
    if leitor.is_encrypted:
        try:
            aberto = leitor.decrypt("")
        except Exception:
            aberto = 0
        if not aberto:
            sair(erro="criptografado")
    total = len(leitor.pages)
    if total > max_paginas:
        sair(erro="paginas_demais", total=total)
    paginas, usados, truncado = [], 0, False
    for pagina in leitor.pages:
        try:
            texto = pagina.extract_text() or ""
        except Exception:
            texto = ""
        if len(texto) > max_pagina:
            texto, truncado = texto[:max_pagina], True
        if usados + len(texto) > max_total:
            texto, truncado = texto[: max(0, max_total - usados)], True
        usados += len(texto)
        paginas.append(texto)
    sair(paginas=paginas, total=total, truncado=truncado)
except SystemExit:
    raise
except MemoryError:
    sair(erro="memoria")
except Exception as erro:
    sair(erro="ilegivel", tipo=type(erro).__name__)
"""


def validar_cabecalho(conteudo: bytes) -> None:
    if not conteudo:
        raise PdfInvalido("Arquivo vazio.")
    if len(conteudo) > TAMANHO_MAXIMO_BYTES:
        raise PdfInvalido(f"Arquivo acima de {TAMANHO_MAXIMO_BYTES // (1024 * 1024)} MB.")
    if b"%PDF-" not in conteudo[:1024]:
        raise PdfInvalido("O arquivo não é um PDF válido (o conteúdo não começa como PDF, qualquer que seja a extensão).")


def avisos_de_conteudo_ativo(conteudo: bytes) -> list[str]:
    achados = sorted({m.decode() for m in _MARCADORES_ATIVOS if m in conteudo})
    if not achados:
        return []
    return [f"O PDF contém marcadores de conteúdo ativo ({', '.join(achados)}). Nada foi executado: só o texto foi lido."]


def extrair_texto(conteudo: bytes, *, max_paginas: int = MAX_PAGINAS, timeout: float = TIMEOUT_SEGUNDOS) -> TextoPdf:
    """Levanta `PdfInvalido` para qualquer recusa. Nunca levanta exceção do leitor."""
    validar_cabecalho(conteudo)
    avisos = avisos_de_conteudo_ativo(conteudo)
    try:
        # `-E`: ignora variáveis PYTHON*; o filho só roda o código deste módulo.
        processo = subprocess.run(
            [sys.executable, "-E", "-c", _TRABALHADOR, str(max_paginas), str(MAX_CHARS_PAGINA), str(MAX_CHARS_TOTAL), str(LIMITE_MEMORIA_BYTES)],
            input=conteudo, capture_output=True, timeout=timeout, check=False,
        )
    except subprocess.TimeoutExpired as erro:
        raise PdfInvalido(f"A leitura do PDF excedeu o tempo limite de {int(timeout)} s e foi interrompida.") from erro
    if processo.returncode != 0 or not processo.stdout:
        raise PdfInvalido("Não foi possível ler o PDF (arquivo corrompido ou acima dos limites de memória).")
    try:
        resposta = json.loads(processo.stdout.decode("utf-8", errors="replace"))
    except ValueError as erro:
        raise PdfInvalido("Não foi possível ler o PDF.") from erro
    codigo = resposta.get("erro")
    if codigo == "criptografado":
        raise PdfInvalido("O PDF é protegido por senha. Envie uma versão sem proteção.")
    if codigo == "paginas_demais":
        raise PdfInvalido(f"O PDF tem {resposta.get('total')} páginas; o limite é {max_paginas}. Envie só o trecho com as demonstrações.")
    if codigo == "memoria":
        raise PdfInvalido("O PDF excede o limite de memória de leitura.")
    if codigo:
        raise PdfInvalido("Não foi possível ler o PDF (arquivo corrompido ou fora do padrão).")
    paginas = [_CONTROLE.sub(" ", p) for p in resposta.get("paginas", [])]
    if resposta.get("truncado"):
        avisos.append("Parte do texto foi descartada por exceder os limites de leitura; os indicadores podem estar incompletos.")
    if not any(p.strip() for p in paginas):
        avisos.append("O PDF não tem camada de texto (provavelmente digitalizado). OCR não está disponível: nada foi extraído.")
    return TextoPdf(paginas=paginas, total_paginas=int(resposta.get("total", len(paginas))), truncado=bool(resposta.get("truncado")), avisos=avisos)
