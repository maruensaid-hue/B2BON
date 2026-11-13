"""Descadastro pelo link do e-mail — endpoints públicos, o destinatário não é usuário autenticado.

GET só mostra a página de confirmação; quem descadastra é o POST (botão da página ou o "Cancelar inscrição" do Gmail/Outlook,
RFC 8058). Antes o GET já descadastrava, e o filtro de segurança de e-mail corporativo, que abre todo link para verificar,
descadastrou 4 pessoas segundos depois do envio (visto em 13/11/2026)."""

import html

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.services import campanha_service, optout_service
from app.services.errors import ValidacaoFalhou

router = APIRouter(prefix="/opt-out", tags=["opt-out"])

_PAGINA = """<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex"><title>{titulo}</title>
<style>
body{{margin:0;font-family:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;background:#f5f5f4;color:#1c1917}}
main{{max-width:440px;margin:12vh auto 0;padding:32px 24px;background:#fff;border-radius:12px;box-shadow:0 1px 3px rgba(0,0,0,.08)}}
h1{{font-size:1.25rem;margin:0 0 12px}} p{{line-height:1.5;margin:0 0 20px}}
button{{font:inherit;font-weight:600;padding:12px 20px;border:0;border-radius:8px;background:#1c1917;color:#fff;cursor:pointer;width:100%}}
</style></head><body><main><h1>{titulo}</h1><p>{texto}</p>{formulario}</main></body></html>"""

_FORMULARIO = '<form method="post"><button type="submit">Confirmar descadastro</button></form>'


def _pagina(titulo: str, texto: str, formulario: str = "", status_code: int = 200) -> HTMLResponse:
    corpo = _PAGINA.format(titulo=html.escape(titulo), texto=html.escape(texto), formulario=formulario)
    return HTMLResponse(corpo, status_code=status_code)


def _confirmacao(validar) -> HTMLResponse:
    try:
        validar()
    except ValidacaoFalhou:
        return _link_invalido()
    return _pagina("Não quer mais receber estes e-mails?", "Confirme abaixo e você não recebe mais mensagens deste remetente.", _FORMULARIO)


def _concluido(processar) -> HTMLResponse:
    try:
        processar()
    except ValidacaoFalhou:
        return _link_invalido()
    return _pagina("Pronto, descadastro feito.", "Você não vai mais receber mensagens deste remetente.")


def _link_invalido() -> HTMLResponse:
    return _pagina("Link inválido", "Este link de descadastro não é válido. Responda ao e-mail pedindo para sair da lista.", status_code=422)


@router.get("/email/{token}", response_class=HTMLResponse)
def confirmar_optout_email(token: str) -> HTMLResponse:
    return _confirmacao(lambda: optout_service.validar_token(token))


@router.post("/email/{token}", response_class=HTMLResponse)
def optout_email(token: str, db: Session = Depends(get_db)) -> HTMLResponse:
    """Link no e-mail (E9-H2)."""
    return _concluido(lambda: optout_service.processar_por_token(db, token))


@router.get("/campanha/{token}", response_class=HTMLResponse)
def confirmar_optout_campanha(token: str) -> HTMLResponse:
    return _confirmacao(lambda: campanha_service.validar_token_optout(token))


@router.post("/campanha/{token}", response_class=HTMLResponse)
def optout_campanha(token: str, db: Session = Depends(get_db)) -> HTMLResponse:
    """Descadastro de campanha (e-mail de marketing/vendas) — mesmo padrão do opt-out de cadência acima."""
    return _concluido(lambda: campanha_service.processar_optout_por_token(db, token))
