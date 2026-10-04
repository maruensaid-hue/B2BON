"""Rotas PÚBLICAS do Integration Hub (D-087) — sem JWT, por natureza:

- callback OAuth: quem chama é o navegador voltando do CRM. Só valida o
  `state` cifrado, troca o código e redireciona para a tela, que conclui
  com o login do MESMO usuário (ver `integrations/oauth.py`). Nunca cria
  conexão aqui e nunca põe token na URL.
- webhook de entrada: o CRM avisa que algo mudou. Token secreto na URL
  (só o hash no banco); só marca a conexão para o cron. Não lê o corpo,
  não devolve dado, 404 genérico para token inválido.
"""

from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.contexts.integrations import contract as integracoes
from app.core.config import settings
from app.services.errors import NaoEncontrado

router = APIRouter(prefix="/hub-integracoes", tags=["hub-integracoes-publico"])

_ACK_SALESFORCE = (
    '<?xml version="1.0" encoding="UTF-8"?><soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/">'
    '<soapenv:Body><notificationsResponse xmlns="http://soap.sforce.com/2005/09/outbound"><Ack>true</Ack>'
    "</notificationsResponse></soapenv:Body></soapenv:Envelope>"
)


def _tela(**params: str) -> RedirectResponse:
    return RedirectResponse(f"{settings.url_base_frontend.rstrip('/')}/admin/api?{urlencode(params)}", status_code=303)


@router.get("/oauth/{sistema}/callback", include_in_schema=False)
def callback_oauth(sistema: str, code: str | None = None, state: str | None = None, error: str | None = None,
                   db: Session = Depends(get_db)) -> RedirectResponse:
    if error or not code or not state:
        return _tela(oauth_erro="O CRM não autorizou a conexão.")
    oauth = integracoes.obter_oauth()
    try:
        referencia = oauth.callback(db, sistema, code, state)
    except oauth.ErroOauth as erro:
        db.rollback()
        return _tela(oauth_erro=str(erro))
    return _tela(oauth=referencia)


@router.post("/webhook/{token}", status_code=202, include_in_schema=False)
def webhook_entrada(token: str, request: Request, db: Session = Depends(get_db)) -> Response:
    tamanho = request.headers.get("content-length")
    entrada = integracoes.obter_entrada()
    if tamanho and tamanho.isdigit() and int(tamanho) > entrada.TAMANHO_MAXIMO:
        return Response(status_code=413)
    if not entrada.receber(db, token):
        raise NaoEncontrado("Não encontrado.")
    if "xml" in (request.headers.get("content-type") or ""):  # Outbound Message do Salesforce exige ACK SOAP
        return Response(content=_ACK_SALESFORCE, media_type="text/xml", status_code=200)
    return Response(status_code=202)
