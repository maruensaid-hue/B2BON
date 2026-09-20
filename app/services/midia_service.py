import io
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from app.services.errors import RegraNegocioViolada, ValidacaoFalhou

TIPOS_IMAGEM_PERMITIDOS = {"image/jpeg", "image/png", "image/webp", "image/gif"}
TIPOS_VIDEO_PERMITIDOS = {"video/mp4", "video/webm", "video/quicktime"}

# Tetos de entrada generosos (câmera de celular) — o corte real de
# espaço em disco (raio-X pós-incidente do Neon, ver
# project_neon_disk_full_recorte_cnpj) vem da COMPRESSÃO abaixo, não
# desses tetos; eles só evitam gastar CPU tentando comprimir um
# arquivo absurdo.
TAMANHO_MAXIMO_IMAGEM_ENTRADA_BYTES = 12 * 1024 * 1024
TAMANHO_MAXIMO_VIDEO_ENTRADA_BYTES = 80 * 1024 * 1024

_DIMENSAO_MAXIMA_IMAGEM = 1600
_QUALIDADE_JPEG = 82

_DURACAO_MAXIMA_VIDEO_SEGUNDOS = 180
_LARGURA_MAXIMA_VIDEO = 1280
_CRF_VIDEO = 28
_TIMEOUT_FFMPEG_SEGUNDOS = 120


def comprimir_imagem(conteudo: bytes) -> bytes:
    """Reencoda em JPEG, redimensionando o lado maior pra no máximo
    _DIMENSAO_MAXIMA_IMAGEM — mesma cautela de espaço do raio-X do Neon
    (Fase 0.5-B/incidente 2026-09-11): sem isso, uma foto de celular
    de 12MB ia direto pro blob do Postgres sem nenhum corte. Converte
    tudo pra RGB (perde transparência de PNG/GIF) — troca aceitável
    num feed de rede social em troca de compressão real."""
    if len(conteudo) > TAMANHO_MAXIMO_IMAGEM_ENTRADA_BYTES:
        limite_mb = TAMANHO_MAXIMO_IMAGEM_ENTRADA_BYTES // (1024 * 1024)
        raise ValidacaoFalhou(f"Imagem maior que o limite de {limite_mb}MB.")

    try:
        imagem = Image.open(io.BytesIO(conteudo))
        imagem.verify()
        imagem = Image.open(io.BytesIO(conteudo))  # verify() invalida o objeto, reabre pra usar de verdade
        imagem = imagem.convert("RGB")
    except (UnidentifiedImageError, OSError) as erro:
        raise ValidacaoFalhou("O arquivo enviado não é uma imagem válida.") from erro

    if max(imagem.size) > _DIMENSAO_MAXIMA_IMAGEM:
        imagem.thumbnail((_DIMENSAO_MAXIMA_IMAGEM, _DIMENSAO_MAXIMA_IMAGEM))

    saida = io.BytesIO()
    imagem.save(saida, format="JPEG", quality=_QUALIDADE_JPEG, optimize=True)
    return saida.getvalue()


def _duracao_video_segundos(caminho: Path) -> float:
    resultado = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(caminho)],
        capture_output=True,
        text=True,
        timeout=_TIMEOUT_FFMPEG_SEGUNDOS,
    )
    try:
        return float(resultado.stdout.strip())
    except ValueError as erro:
        raise ValidacaoFalhou("O arquivo enviado não é um vídeo válido.") from erro


def comprimir_video(conteudo: bytes) -> bytes:
    """Reencoda com ffmpeg (H.264/CRF 28, largura máx.
    _LARGURA_MAXIMA_VIDEO) antes de gravar o blob — mesma cautela de
    _comprimir_imagem_, mas vídeo cru pode ser ordens de magnitude
    maior, daí o teto de duração (evita um vídeo longo travar o
    processo de upload rodando ffmpeg por minutos numa instância
    Render com CPU compartilhada)."""
    if len(conteudo) > TAMANHO_MAXIMO_VIDEO_ENTRADA_BYTES:
        limite_mb = TAMANHO_MAXIMO_VIDEO_ENTRADA_BYTES // (1024 * 1024)
        raise ValidacaoFalhou(f"Vídeo maior que o limite de {limite_mb}MB.")

    with tempfile.TemporaryDirectory() as diretorio_temp:
        entrada = Path(diretorio_temp) / "entrada"
        saida = Path(diretorio_temp) / "saida.mp4"
        entrada.write_bytes(conteudo)

        duracao = _duracao_video_segundos(entrada)
        if duracao > _DURACAO_MAXIMA_VIDEO_SEGUNDOS:
            minutos = _DURACAO_MAXIMA_VIDEO_SEGUNDOS // 60
            raise ValidacaoFalhou(f"Vídeo mais longo que o limite de {minutos} minutos.")

        try:
            resultado = subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-i", str(entrada),
                    "-vf", f"scale='min({_LARGURA_MAXIMA_VIDEO},iw)':-2",
                    "-c:v", "libx264",
                    "-crf", str(_CRF_VIDEO),
                    "-preset", "veryfast",
                    "-c:a", "aac",
                    "-b:a", "128k",
                    "-movflags", "+faststart",
                    str(saida),
                ],
                capture_output=True,
                timeout=_TIMEOUT_FFMPEG_SEGUNDOS,
            )
        except subprocess.TimeoutExpired as erro:
            raise RegraNegocioViolada("A compressão do vídeo demorou demais e foi cancelada.") from erro

        if resultado.returncode != 0 or not saida.exists():
            raise ValidacaoFalhou("O arquivo enviado não é um vídeo válido.")

        return saida.read_bytes()
