"""Conectar CRM com 1 clique (D-087, TD-068): OAuth 2.0 authorization code
com os apps da B2B ON no Salesforce, HubSpot e Pipedrive. RD Station CRM
(API v1) continua por token.

Segurança (anti-CSRF e anti-sequestro de conexão):
1. `iniciar` (admin logado) gera o `state` = token Fernet (autenticado,
   expira em 10 min) com tenant, usuário, CRM, nonce e o `code_verifier` do
   PKCE (Salesforce). Nada disso é adivinhável nem alterável.
2. `callback` (público: quem chama é o navegador vindo do CRM) valida o
   `state`, troca o `code` por tokens e guarda-os CRIPTOGRAFADOS numa
   autorização pendente de 10 min. NÃO cria conexão.
3. `concluir` (admin logado) só cria a conexão se o usuário logado for o
   mesmo que iniciou. Assim um atacante que faça a vítima abrir o callback
   com o código DELE não consegue plantar o CRM dele no tenant da vítima,
   nem levar o CRM da vítima para o tenant dele.
Tokens nunca vão para URL, log ou resposta. Escopos mínimos: leitura sempre;
escrita só quando o admin pede (PREDATOR/MAP → CRM).
"""

import base64
import hashlib
import json
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

from cryptography.fernet import InvalidToken
from sqlalchemy.orm import Session

from app.contexts.integrations.adapters import http_base, pipedrive, salesforce
from app.contexts.integrations.adapters.http_base import ClienteHttp, host_permitido
from app.core.config import settings
from app.core.crypto import obter_fernet
from app.models.integracao_crm import AutorizacaoOauthPendente

VALIDADE = timedelta(minutes=10)


@dataclass(frozen=True)
class Provedor:
    autorizar: str
    token_base: str
    token_caminho: str
    escopos_leitura: str
    escopos_escrita: str
    pkce: bool = False
    basic_auth: bool = False


PROVEDORES = {
    "salesforce": Provedor(
        autorizar="https://login.salesforce.com/services/oauth2/authorize",
        token_base="https://login.salesforce.com", token_caminho="/services/oauth2/token",
        escopos_leitura="api refresh_token", escopos_escrita="api refresh_token", pkce=True,
    ),
    "hubspot": Provedor(
        autorizar="https://app.hubspot.com/oauth/authorize",
        token_base="https://api.hubapi.com", token_caminho="/oauth/v1/token",
        escopos_leitura="oauth crm.objects.companies.read crm.objects.contacts.read crm.objects.deals.read crm.schemas.deals.read",
        escopos_escrita=("oauth crm.objects.companies.read crm.objects.contacts.read crm.objects.deals.read crm.schemas.deals.read "
                         "crm.objects.companies.write crm.objects.contacts.write crm.objects.deals.write "
                         "crm.schemas.companies.write crm.schemas.contacts.write"),
    ),
    # Pipedrive: escopos ficam no cadastro do app no Marketplace (não vão na URL).
    "pipedrive": Provedor(
        autorizar="https://oauth.pipedrive.com/oauth/authorize",
        token_base="https://oauth.pipedrive.com", token_caminho="/oauth/token",
        escopos_leitura="", escopos_escrita="", basic_auth=True,
    ),
}
_SANDBOX_SALESFORCE = "https://test.salesforce.com"


class ErroOauth(Exception):
    """Mensagem segura para o usuário (sem token, sem código)."""


def _app(sistema: str) -> tuple[str, str]:
    return getattr(settings, f"oauth_{sistema}_client_id", ""), getattr(settings, f"oauth_{sistema}_client_secret", "")


def disponivel(sistema: str) -> bool:
    return sistema in PROVEDORES and all(_app(sistema))


def redirect_uri(sistema: str) -> str:
    return f"{settings.url_base_api.rstrip('/')}/hub-integracoes/oauth/{sistema}/callback"


def _pkce() -> tuple[str, str]:
    verificador = secrets.token_urlsafe(64)[:96]
    desafio = base64.urlsafe_b64encode(hashlib.sha256(verificador.encode()).digest()).rstrip(b"=").decode()
    return verificador, desafio


def iniciar(tenant_id: str, usuario_id: int, sistema: str, nome: str, escrita: bool, sandbox: bool = False) -> str:
    """URL de autorização do CRM (o frontend redireciona o navegador)."""
    if not disponivel(sistema):
        raise ErroOauth("Conexão com 1 clique ainda não está disponível para este CRM. Use o token.")
    if sandbox and sistema != "salesforce":
        raise ErroOauth("Ambiente sandbox só existe no Salesforce.")
    provedor = PROVEDORES[sistema]
    client_id, _ = _app(sistema)
    verificador, desafio = _pkce() if provedor.pkce else (None, None)
    state = obter_fernet().encrypt(json.dumps({
        "t": tenant_id, "u": usuario_id, "s": sistema, "n": nome[:100], "e": bool(escrita), "sb": bool(sandbox),
        "v": verificador, "x": secrets.token_urlsafe(16),
    }).encode()).decode()
    params = {"client_id": client_id, "redirect_uri": redirect_uri(sistema), "response_type": "code", "state": state}
    escopos = provedor.escopos_escrita if escrita else provedor.escopos_leitura
    if escopos:
        params["scope"] = escopos
    if desafio:
        params["code_challenge"], params["code_challenge_method"] = desafio, "S256"
    autorizar = provedor.autorizar.replace("https://login.salesforce.com", _SANDBOX_SALESFORCE) if sandbox else provedor.autorizar
    return f"{autorizar}?{urlencode(params)}"


def _ler_state(sistema: str, state: str) -> dict:
    try:
        dados = json.loads(obter_fernet().decrypt(state.encode(), ttl=int(VALIDADE.total_seconds())))
    except (InvalidToken, ValueError, TypeError) as erro:
        raise ErroOauth("Autorização expirada ou inválida. Tente conectar de novo.") from erro
    if dados.get("s") != sistema:
        raise ErroOauth("Autorização de outro CRM.")
    return dados


def _trocar_codigo(sistema: str, codigo: str, dados: dict) -> dict:
    provedor = PROVEDORES[sistema]
    client_id, client_secret = _app(sistema)
    base = _SANDBOX_SALESFORCE if (sistema == "salesforce" and dados.get("sb")) else provedor.token_base
    corpo = {"grant_type": "authorization_code", "code": codigo, "redirect_uri": redirect_uri(sistema)}
    auth = None
    if provedor.basic_auth:
        auth = (client_id, client_secret)
    else:
        corpo.update({"client_id": client_id, "client_secret": client_secret})
    if dados.get("v"):
        corpo["code_verifier"] = dados["v"]
    try:
        resposta = ClienteHttp(sistema, base, {"Accept": "application/json"}, http_base.TRANSPORTE_PADRAO).post_form(provedor.token_caminho, corpo, auth=auth)
    except Exception as erro:  # noqa: BLE001 — nunca devolve o corpo (pode ecoar segredo)
        raise ErroOauth("O CRM recusou a autorização. Tente conectar de novo.") from erro
    if not resposta.get("access_token"):
        raise ErroOauth("O CRM não devolveu o acesso. Tente conectar de novo.")
    credenciais = {"oauth_app": "b2bon", "access_token": resposta["access_token"]}
    if resposta.get("refresh_token"):
        credenciais["refresh_token"] = resposta["refresh_token"]
    if sistema == "salesforce":
        instancia = resposta.get("instance_url", "")
        if not host_permitido(instancia, salesforce.HOSTS_API):
            raise ErroOauth("Instância Salesforce inválida.")
        credenciais["instance_url"] = instancia
        credenciais["login_url"] = base
    if sistema == "pipedrive":
        dominio = resposta.get("api_domain", "")
        if not host_permitido(dominio, pipedrive.HOSTS_EMPRESA):
            raise ErroOauth("Domínio Pipedrive inválido.")
        credenciais["api_domain"] = dominio
    return credenciais


def callback(db: Session, sistema: str, codigo: str, state: str) -> str:
    """Troca o código e guarda a autorização pendente. Devolve a referência
    (aleatória) que o frontend usa em `concluir`."""
    if sistema not in PROVEDORES:
        raise ErroOauth("CRM desconhecido.")
    dados = _ler_state(sistema, state)
    credenciais = _trocar_codigo(sistema, codigo, dados)
    referencia = secrets.token_urlsafe(32)
    credenciais["_escrita"] = dados.get("e", False)  # removido antes de virar conexão
    db.add(AutorizacaoOauthPendente(
        id=referencia, tenant_id=dados["t"], usuario_id=int(dados["u"]), sistema=sistema, nome=dados.get("n") or sistema,
        credenciais=json.dumps(credenciais), expira_em=datetime.now(UTC) + VALIDADE,
    ))
    db.query(AutorizacaoOauthPendente).filter(AutorizacaoOauthPendente.expira_em < datetime.now(UTC).replace(tzinfo=None)).delete()
    db.commit()
    return referencia


def consumir(db: Session, referencia: str, tenant_id: str, usuario_id: int) -> tuple[str, str, dict, bool]:
    """(sistema, nome, credenciais, escrita) — só para o MESMO usuário que
    iniciou; uso único (apagada aqui)."""
    pendente = db.get(AutorizacaoOauthPendente, referencia) if referencia else None
    agora = datetime.now(UTC).replace(tzinfo=None)
    if pendente is None or pendente.tenant_id != tenant_id or pendente.usuario_id != usuario_id or pendente.expira_em.replace(tzinfo=None) < agora:
        raise ErroOauth("Autorização não encontrada ou expirada. Tente conectar de novo.")
    credenciais = json.loads(pendente.credenciais)
    escrita = bool(credenciais.pop("_escrita", False))
    db.delete(pendente)
    return pendente.sistema, pendente.nome, credenciais, escrita
