import shutil

import pytest

# TD-034 (Fase 1): testes de vídeo chamam ffmpeg/ffprobe de verdade. O CI
# instala o ffmpeg (`ci.yml`) e roda todos; fora dele, pula em vez de
# falhar com `FileNotFoundError` — falha de ambiente não é regressão.
requer_ffmpeg = pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="ffmpeg/ffprobe não instalado neste ambiente",
)
