import io
import subprocess
import tempfile
from pathlib import Path

import pytest
from PIL import Image

from app.services import midia_service
from app.services.errors import ValidacaoFalhou


def _gerar_imagem_bytes(largura: int, altura: int, formato: str = "PNG") -> bytes:
    imagem = Image.new("RGB", (largura, altura), color=(200, 40, 40))
    saida = io.BytesIO()
    imagem.save(saida, format=formato)
    return saida.getvalue()


def _gerar_video_bytes(duracao_segundos: float = 1.0) -> bytes:
    with tempfile.TemporaryDirectory() as diretorio_temp:
        saida = Path(diretorio_temp) / "gerado.mp4"
        subprocess.run(
            [
                "ffmpeg", "-y",
                "-f", "lavfi", "-i", f"testsrc=duration={duracao_segundos}:size=320x240:rate=10",
                "-pix_fmt", "yuv420p",
                str(saida),
            ],
            capture_output=True,
            timeout=30,
            check=True,
        )
        return saida.read_bytes()


def test_comprimir_imagem_redimensiona_e_reencoda_em_jpeg():
    original = _gerar_imagem_bytes(3000, 2000)

    comprimida = midia_service.comprimir_imagem(original)

    resultado = Image.open(io.BytesIO(comprimida))
    assert resultado.format == "JPEG"
    assert max(resultado.size) <= midia_service._DIMENSAO_MAXIMA_IMAGEM
    assert len(comprimida) < len(original)


def test_comprimir_imagem_mantem_imagem_pequena_sem_redimensionar():
    original = _gerar_imagem_bytes(200, 100)

    comprimida = midia_service.comprimir_imagem(original)

    resultado = Image.open(io.BytesIO(comprimida))
    assert resultado.size == (200, 100)


def test_comprimir_imagem_rejeita_arquivo_invalido():
    with pytest.raises(ValidacaoFalhou):
        midia_service.comprimir_imagem(b"isto claramente nao e uma imagem")


def test_comprimir_imagem_rejeita_maior_que_limite(monkeypatch):
    monkeypatch.setattr(midia_service, "TAMANHO_MAXIMO_IMAGEM_ENTRADA_BYTES", 10)

    with pytest.raises(ValidacaoFalhou):
        midia_service.comprimir_imagem(_gerar_imagem_bytes(50, 50))


def test_comprimir_video_reencoda_para_mp4_valido():
    original = _gerar_video_bytes(duracao_segundos=1.0)

    comprimido = midia_service.comprimir_video(original)

    assert len(comprimido) > 0
    assert b"ftyp" in comprimido[:32]


def test_comprimir_video_rejeita_arquivo_invalido():
    with pytest.raises(ValidacaoFalhou):
        midia_service.comprimir_video(b"isto claramente nao e um video")


def test_comprimir_video_rejeita_maior_que_limite(monkeypatch):
    monkeypatch.setattr(midia_service, "TAMANHO_MAXIMO_VIDEO_ENTRADA_BYTES", 10)

    with pytest.raises(ValidacaoFalhou):
        midia_service.comprimir_video(_gerar_video_bytes())


def test_comprimir_video_rejeita_duracao_maior_que_limite(monkeypatch):
    monkeypatch.setattr(midia_service, "_DURACAO_MAXIMA_VIDEO_SEGUNDOS", 0.5)
    video_de_2_segundos = _gerar_video_bytes(duracao_segundos=2.0)

    with pytest.raises(ValidacaoFalhou):
        midia_service.comprimir_video(video_de_2_segundos)
