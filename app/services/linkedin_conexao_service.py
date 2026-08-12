import csv
import io
import unicodedata
from datetime import date, datetime
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from app.models.conexao_linkedin import ConexaoLinkedin
from app.models.decisor import Decisor
from app.services.errors import ValidacaoFalhou

# LinkedIn embute o blob direto na resposta (sem multipart) — mesmo teto já
# usado para materiais de oferta, texto puro é bem mais leve que PDF/DOCX.
TAMANHO_MAXIMO_CSV_BYTES = 15 * 1024 * 1024

_COLUNAS_CABECALHO_ESPERADAS = {"first name", "url"}


def _normalizar_texto(texto: str) -> str:
    sem_acentos = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
    return " ".join(sem_acentos.lower().split())


def _normalizar_url_perfil(url: str | None) -> str | None:
    if not url or not url.strip():
        return None
    analisada = urlparse(url.strip() if "://" in url else f"https://{url.strip()}")
    caminho = analisada.path.rstrip("/")
    host = analisada.netloc.lower().removeprefix("www.")
    return f"{host}{caminho}".lower() or None


def _parsear_data(texto: str | None) -> date | None:
    if not texto or not texto.strip():
        return None
    for formato in ("%d %b %Y", "%Y-%m-%d", "%m/%d/%y", "%m/%d/%Y"):
        try:
            return datetime.strptime(texto.strip(), formato).date()
        except ValueError:
            continue
    return None


def _localizar_inicio_cabecalho(linhas: list[str]) -> int:
    """O export oficial do LinkedIn traz ~3 linhas de "Notes:" antes do
    cabeçalho real — procura a linha que de fato tem "First Name" e "URL"."""
    for indice, linha in enumerate(linhas):
        colunas = {coluna.strip().lower() for coluna in linha.split(",")}
        if _COLUNAS_CABECALHO_ESPERADAS.issubset(colunas):
            return indice
    raise ValidacaoFalhou(
        "Não foi possível reconhecer o CSV como um export de conexões do LinkedIn "
        "(colunas 'First Name'/'URL' não encontradas)."
    )


def importar_csv(db: Session, tenant_id: str, usuario_id: int, conteudo_csv: str) -> int:
    if not conteudo_csv or not conteudo_csv.strip():
        raise ValidacaoFalhou("Arquivo vazio.")
    if len(conteudo_csv.encode("utf-8")) > TAMANHO_MAXIMO_CSV_BYTES:
        limite_mb = TAMANHO_MAXIMO_CSV_BYTES // (1024 * 1024)
        raise ValidacaoFalhou(f"Arquivo maior que o limite de {limite_mb}MB.")

    linhas = conteudo_csv.splitlines()
    inicio = _localizar_inicio_cabecalho(linhas)
    leitor = csv.DictReader(io.StringIO("\n".join(linhas[inicio:])))

    conexoes: list[ConexaoLinkedin] = []
    for linha in leitor:
        nome_completo = " ".join(
            parte.strip() for parte in (linha.get("First Name"), linha.get("Last Name")) if parte and parte.strip()
        )
        if not nome_completo:
            continue
        conexoes.append(
            ConexaoLinkedin(
                tenant_id=tenant_id,
                usuario_id=usuario_id,
                nome_completo=nome_completo,
                url_perfil=_normalizar_url_perfil(linha.get("URL")),
                email=(linha.get("Email Address") or "").strip() or None,
                empresa_atual=(linha.get("Company") or "").strip() or None,
                cargo_atual=(linha.get("Position") or "").strip() or None,
                conectado_em=_parsear_data(linha.get("Connected On")),
            )
        )

    if not conexoes:
        raise ValidacaoFalhou("Nenhuma conexão válida encontrada no arquivo.")

    # Reupload substitui — evita acumular duplicado a cada nova exportação.
    db.query(ConexaoLinkedin).filter_by(tenant_id=tenant_id, usuario_id=usuario_id).delete()
    db.add_all(conexoes)
    db.commit()
    return len(conexoes)


def status(db: Session, tenant_id: str, usuario_id: int) -> dict:
    total = db.query(ConexaoLinkedin).filter_by(tenant_id=tenant_id, usuario_id=usuario_id).count()
    ultima = (
        db.query(ConexaoLinkedin)
        .filter_by(tenant_id=tenant_id, usuario_id=usuario_id)
        .order_by(ConexaoLinkedin.criado_em.desc())
        .first()
    )
    return {"total": total, "atualizado_em": ultima.criado_em if ultima else None}


def esta_conectado(db: Session, tenant_id: str, usuario_id: int, decisor: Decisor) -> bool:
    """Heurística simples (URL de perfil, com fallback por nome) — é só uma
    sugestão para o vendedor, não uma verdade absoluta: falso negativo por
    variação de nome/URL é esperado e aceitável."""
    conexoes = db.query(ConexaoLinkedin).filter_by(tenant_id=tenant_id, usuario_id=usuario_id).all()
    if not conexoes:
        return False

    url_decisor = _normalizar_url_perfil(decisor.linkedin_url)
    if url_decisor:
        if any(conexao.url_perfil == url_decisor for conexao in conexoes):
            return True

    nome_decisor = _normalizar_texto(decisor.nome)
    return any(_normalizar_texto(conexao.nome_completo) == nome_decisor for conexao in conexoes)
