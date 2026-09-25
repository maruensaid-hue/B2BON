"""Registro das fontes de licitação e o estado real de cada uma."""

from app.core.config import settings

FONTES = {
    "MANUAL": {"nome": "Cadastro manual", "status": "DISPONIVEL"},
    "UPLOAD": {"nome": "Upload de edital/TR (PDF ou texto)", "status": "DISPONIVEL"},
    "PNCP": {"nome": "Portal Nacional de Contratações Públicas", "status": "EXPERIMENTAL"},
}


def fontes() -> list[dict]:
    return [
        {"id": chave, **dados, "habilitada": chave != "PNCP" or settings.pncp_habilitado}
        for chave, dados in FONTES.items()
    ]
