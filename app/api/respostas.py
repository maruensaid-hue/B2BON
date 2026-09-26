"""Respostas HTTP compartilhadas pelas rotas."""

from fastapi.responses import Response


def arquivo_com_hash(conteudo: bytes | None, tipo_mime: str, nome: str, sha256: str) -> Response:
    """Download de evidência: nome neutro (não repete o nome enviado por terceiros) e o hash para conferência."""
    return Response(content=conteudo or b"", media_type=tipo_mime,
                    headers={"Content-Disposition": f'attachment; filename="{nome}"', "X-Content-SHA256": sha256})
