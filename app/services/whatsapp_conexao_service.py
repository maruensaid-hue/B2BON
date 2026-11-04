"""Conexão do número de WhatsApp de cada empresa: botão "Conectar com a Meta" (cadastro incorporado) e "Testar conexão".

Cada tenant (ou cliente de contratação individual) usa o PRÓPRIO número. No cadastro incorporado a pessoa faz login na Meta numa
janela da própria Meta, escolhe ou cria a conta e o número, e o navegador devolve ao B2B ON um código de uso único e os IDs. Aqui:
1. o código vira o token da empresa (troca feita com o segredo do app, que nunca vai ao navegador);
2. o app é inscrito na conta do WhatsApp (sem isso as respostas dos clientes não chegam ao webhook);
3. o número é registrado na API de nuvem com um PIN novo de 6 dígitos (guardado criptografado);
4. número, nome verificado e qualidade são lidos da Meta e mostrados na tela como prova de que ficou ligado.
O passo 3 pode falhar sem impedir a conexão (número já registrado com outro PIN): fica o aviso com o que fazer.
"""

import logging
import secrets
from datetime import UTC, datetime

import httpx
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.configuracao_whatsapp import ConfiguracaoWhatsApp
from app.providers.channels.whatsapp.meta import MetaWhatsAppProvider
from app.services import auditoria_service
from app.services.errors import RegraNegocioViolada, ValidacaoFalhou

_TIMEOUT = 20.0
logger = logging.getLogger(__name__)


def _graph() -> str:
    return f"https://graph.facebook.com/{settings.meta_graph_versao}"


def parametros() -> dict:
    """O que o navegador precisa para abrir a janela da Meta (nada secreto)."""
    disponivel = bool(settings.meta_app_id and settings.meta_embedded_signup_config_id and settings.whatsapp_app_secret)
    return {
        "disponivel": disponivel,
        "app_id": settings.meta_app_id if disponivel else None,
        "config_id": settings.meta_embedded_signup_config_id if disponivel else None,
        "graph_versao": settings.meta_graph_versao,
        "retorno": "codigo" if settings.meta_embedded_signup_retorno == "codigo" else "token",
    }


def _registrar_recusa(etapa: str, resposta: httpx.Response | None, **contexto) -> None:
    """Guarda no log a resposta exata da Meta (código, subcódigo, rastreio), sem token nem segredo: é o que permite diagnosticar
    em vez de tentar às cegas."""
    erro = {}
    if resposta is not None:
        try:
            erro = resposta.json().get("error") or {}
        except ValueError:
            erro = {}
    logger.warning(
        "META_CONEXAO_RECUSADA etapa=%s status=%s codigo=%s subcodigo=%s tipo=%s fbtrace=%s mensagem=%s contexto=%s",
        etapa, resposta.status_code if resposta is not None else None, erro.get("code"), erro.get("error_subcode"), erro.get("type"),
        erro.get("fbtrace_id"), (erro.get("message") or "")[:300], contexto,
    )


def _erro_meta(resposta: httpx.Response) -> str:
    try:
        erro = resposta.json().get("error", {})
    except ValueError:
        erro = {}
    return erro.get("error_user_msg") or erro.get("message") or f"HTTP {resposta.status_code}"


def _candidatos_redirect(pagina: str | None) -> list[str | None]:
    """Em que endereço a Meta pode ter amarrado o código. Sem `redirect_uri` é o documentado; mas o código vindo da janela do SDK
    JavaScript às vezes fica preso à página onde o botão foi clicado ("Error validating verification code... redirect_uri", visto
    no staging em 04/11/2026). O código do SDK JavaScript fica amarrado a um endereço interno da própria Meta, e a troca dele
    pede `redirect_uri` PRESENTE e VAZIO (é o que o SDK oficial de PHP da Meta faz com códigos vindos do JS): é a 2ª tentativa.
    Endereço da página por último, só https, sem query nem fragmento (exige o domínio cadastrado no app)."""
    candidatos: list[str | None] = [None, ""]
    pagina = (pagina or "").split("#")[0].split("?")[0].strip()
    if pagina.startswith("https://"):
        origem = "/".join(pagina.split("/")[:3]) + "/"
        for c in (pagina, origem):
            if c not in candidatos:
                candidatos.append(c)
    return candidatos


def _trocar_codigo(codigo: str, pagina: str | None = None) -> str:
    resposta = None
    primeiro_erro = None
    for redirect in _candidatos_redirect(pagina):
        params = {"client_id": settings.meta_app_id, "client_secret": settings.whatsapp_app_secret, "code": codigo}
        if redirect is not None:
            params["redirect_uri"] = redirect
        try:
            resposta = httpx.get(f"{_graph()}/oauth/access_token", params=params, timeout=_TIMEOUT)
        except httpx.HTTPError as erro:
            raise RegraNegocioViolada(f"A Meta não respondeu ao concluir a conexão ({type(erro).__name__}). Tente de novo.") from erro
        if resposta.is_success and resposta.json().get("access_token"):
            return resposta.json()["access_token"]
        erro = _erro_meta(resposta)
        _registrar_recusa("troca_codigo", resposta, redirect=("ausente" if redirect is None else redirect or "vazio"))
        primeiro_erro = primeiro_erro or erro
        if "redirect_uri" not in erro and redirect is None:
            break  # outro motivo (código vencido, segredo errado): tentar outro endereço não adianta
    raise RegraNegocioViolada(f"A Meta não aceitou concluir a conexão: {primeiro_erro}. Clique em Conectar de novo.")


def _inscrever_app(token: str, waba_id: str) -> str | None:
    try:
        resposta = httpx.post(f"{_graph()}/{waba_id}/subscribed_apps", headers={"Authorization": f"Bearer {token}"}, timeout=_TIMEOUT)
    except httpx.HTTPError as erro:
        return f"Não foi possível inscrever o app na sua conta ({type(erro).__name__}): as respostas dos clientes podem não chegar."
    return None if resposta.is_success else f"Inscrição do app na conta recusada: {_erro_meta(resposta)}."


def _registrar_numero(token: str, phone_number_id: str, pin: str) -> str | None:
    try:
        resposta = httpx.post(
            f"{_graph()}/{phone_number_id}/register", headers={"Authorization": f"Bearer {token}"},
            json={"messaging_product": "whatsapp", "pin": pin}, timeout=_TIMEOUT,
        )
    except httpx.HTTPError as erro:
        return f"Não foi possível registrar o número na API ({type(erro).__name__})."
    if resposta.is_success:
        return None
    return (
        f"O número não foi registrado na API: {_erro_meta(resposta)}. Se ele já tinha verificação em duas etapas com outro PIN, "
        "desative-a no WhatsApp Manager e clique em Conectar de novo."
    )


def _debug_token(token: str) -> dict:
    """O que a Meta sabe do token (`debug_token`, consultado com o token do app). `{}` = app não configurado ou Meta sem resposta."""
    if not (settings.meta_app_id and settings.whatsapp_app_secret):
        return {}
    try:
        resposta = httpx.get(
            f"{_graph()}/debug_token",
            params={"input_token": token, "access_token": f"{settings.meta_app_id}|{settings.whatsapp_app_secret}"},
            timeout=_TIMEOUT,
        )
    except httpx.HTTPError:
        return {}
    if not resposta.is_success:
        return {}
    return resposta.json().get("data") or {}


def _token_do_navegador(token_curto: str) -> str:
    """Configuração "token de acesso do usuário": a janela devolve o token. Antes de usar, confere com a Meta que ele é válido e foi
    emitido para ESTE app (um token de outro app colado aqui seria recusado), e troca pelo de longa duração (60 dias)."""
    dados = _debug_token(token_curto)
    if not dados.get("is_valid") or str(dados.get("app_id")) != str(settings.meta_app_id):
        logger.warning("META_CONEXAO_RECUSADA etapa=token_navegador valido=%s app_confere=%s", dados.get("is_valid"),
                       str(dados.get("app_id")) == str(settings.meta_app_id))
        raise RegraNegocioViolada("A Meta não confirmou a autorização deste aplicativo. Clique em Conectar de novo.")
    try:
        resposta = httpx.get(
            f"{_graph()}/oauth/access_token",
            params={"grant_type": "fb_exchange_token", "client_id": settings.meta_app_id, "client_secret": settings.whatsapp_app_secret,
                    "fb_exchange_token": token_curto},
            timeout=_TIMEOUT,
        )
    except httpx.HTTPError as erro:
        raise RegraNegocioViolada(f"A Meta não respondeu ao concluir a conexão ({type(erro).__name__}). Tente de novo.") from erro
    if not resposta.is_success or not resposta.json().get("access_token"):
        _registrar_recusa("token_longo", resposta)
        raise RegraNegocioViolada(f"A Meta não aceitou concluir a conexão: {_erro_meta(resposta)}. Clique em Conectar de novo.")
    return resposta.json()["access_token"]


def validade_do_token(token: str) -> datetime | None:
    """Quando o token vence. `None` = sem prazo, app não configurado ou Meta sem resposta: quem chama não trata isso como erro
    (a validade é aviso, não condição para enviar)."""
    expira = _debug_token(token).get("expires_at")
    # 0 (ou ausente) = o token não vence
    return datetime.fromtimestamp(expira, UTC).replace(tzinfo=None) if isinstance(expira, int) and expira > 0 else None


def _descobrir_ids(token: str) -> tuple[str, str]:
    """Conta do WhatsApp e número autorizados no token, quando a janela da Meta não os mandou ao navegador (a mensagem dela às
    vezes não chega à página, visto no staging em 04/11/2026). A conta vem das permissões do token; o número, da lista da conta."""
    wabas: list[str] = []
    for escopo in _debug_token(token).get("granular_scopes") or []:
        if escopo.get("scope") == "whatsapp_business_management":
            wabas += [str(i) for i in escopo.get("target_ids") or [] if str(i) not in wabas]
    if len(wabas) != 1:
        raise RegraNegocioViolada(
            "Não foi possível identificar a conta do WhatsApp escolhida na janela da Meta"
            + (" (mais de uma foi autorizada)" if wabas else "")
            + ". Clique em Conectar de novo e escolha uma única conta e um único número."
        )
    waba_id = wabas[0]
    try:
        resposta = httpx.get(f"{_graph()}/{waba_id}/phone_numbers", headers={"Authorization": f"Bearer {token}"},
                             params={"fields": "id,display_phone_number"}, timeout=_TIMEOUT)
    except httpx.HTTPError as erro:
        raise RegraNegocioViolada(f"A Meta não respondeu ao listar os números ({type(erro).__name__}). Tente de novo.") from erro
    numeros = [str(n["id"]) for n in (resposta.json().get("data") or []) if n.get("id")] if resposta.is_success else []
    if len(numeros) != 1:
        raise RegraNegocioViolada(
            ("A conta do WhatsApp escolhida não tem número" if not numeros else "A conta do WhatsApp escolhida tem mais de um número")
            + ". Use a configuração manual informando o ID do número, ou deixe só um número na conta e conecte de novo."
        )
    return numeros[0], waba_id


def _salvar(db: Session, tenant_id: str, valores: dict) -> int:
    existente = db.execute(select(ConfiguracaoWhatsApp.id).where(ConfiguracaoWhatsApp.tenant_id == tenant_id)).one_or_none()
    if existente is None:
        config = ConfiguracaoWhatsApp(tenant_id=tenant_id, **valores)
        db.add(config)
        db.flush()
        return config.id
    db.execute(update(ConfiguracaoWhatsApp).where(ConfiguracaoWhatsApp.id == existente.id).values(**valores))
    return existente.id


def conectar(db: Session, tenant_id: str, ator_id: str | None, codigo: str, phone_number_id: str, waba_id: str,
             pagina: str | None = None, access_token: str | None = None) -> dict:
    if not parametros()["disponivel"]:
        raise RegraNegocioViolada("A conexão pela Meta não está disponível nesta instalação: use a configuração manual.")
    if not codigo and not access_token:
        raise ValidacaoFalhou("A janela da Meta não devolveu a autorização. Clique em Conectar e conclua todas as etapas.")
    phone_number_id, waba_id = (phone_number_id or "").strip(), (waba_id or "").strip()
    if (phone_number_id and not phone_number_id.isdigit()) or (waba_id and not waba_id.isdigit()):
        raise ValidacaoFalhou("A janela da Meta devolveu dados do número inválidos. Clique em Conectar de novo.")

    token = _token_do_navegador(access_token) if access_token else _trocar_codigo(codigo, pagina)
    if not (phone_number_id and waba_id):
        phone_number_id, waba_id = _descobrir_ids(token)
    pin = f"{secrets.randbelow(10**6):06d}"
    aviso_registro = _registrar_numero(token, phone_number_id, pin)
    avisos = [a for a in (_inscrever_app(token, waba_id), aviso_registro) if a]
    info = MetaWhatsAppProvider(token, phone_number_id, waba_id).info_numero()
    expira_em = validade_do_token(token)

    config_id = _salvar(db, tenant_id, {
        "access_token": token, "phone_number_id": phone_number_id, "business_account_id": waba_id, "origem_conexao": "meta_conectar",
        "pin_registro": pin if aviso_registro is None else None,
        "numero_exibicao": info.numero_exibicao, "nome_verificado": info.nome_verificado, "qualidade": info.qualidade,
        "token_expira_em": expira_em,
    })
    auditoria_service.registrar(db, tenant_id, "whatsapp_conectado_pela_meta", "configuracao_whatsapp", config_id, ator_id,
                                {"avisos": len(avisos), "numero": info.numero_exibicao})
    db.commit()
    return {"numero_exibicao": info.numero_exibicao, "nome_verificado": info.nome_verificado, "qualidade": info.qualidade, "avisos": avisos,
            "token_expira_em": expira_em}


def testar(db: Session, tenant_id: str, provider) -> dict:
    """Pergunta à Meta pelo número configurado e guarda o que ela disse: prova de que token e IDs funcionam."""
    info = provider.info_numero()
    expira_em = None
    if info.erro is None:
        try:
            token = db.execute(select(ConfiguracaoWhatsApp.access_token).where(ConfiguracaoWhatsApp.tenant_id == tenant_id)).scalar()
        except Exception:  # noqa: BLE001 — token que não decifra: a validade fica sem consulta, o teste em si já passou
            token = None
        expira_em = validade_do_token(token) if token else None
        db.execute(
            update(ConfiguracaoWhatsApp).where(ConfiguracaoWhatsApp.tenant_id == tenant_id)
            .values(numero_exibicao=info.numero_exibicao, nome_verificado=info.nome_verificado, qualidade=info.qualidade,
                    token_expira_em=expira_em)
        )
        db.commit()
    return {"ok": info.erro is None, "numero_exibicao": info.numero_exibicao, "nome_verificado": info.nome_verificado,
            "qualidade": info.qualidade, "erro": info.erro, "token_expira_em": expira_em}


def definir_direct_send(db: Session, tenant_id: str, ator_id: str | None, habilitado: bool) -> None:
    """O admin declara que a conta é elegível ao Direct Send (a Meta mostra isso no WhatsApp Manager). Ligar limpa o motivo antigo."""
    existente = db.execute(select(ConfiguracaoWhatsApp.id).where(ConfiguracaoWhatsApp.tenant_id == tenant_id)).one_or_none()
    if existente is None:
        raise RegraNegocioViolada("Conecte o número de WhatsApp antes.")
    valores = {"direct_send_habilitado": habilitado}
    if habilitado:
        valores["direct_send_motivo_desligado"] = None
    db.execute(update(ConfiguracaoWhatsApp).where(ConfiguracaoWhatsApp.id == existente.id).values(**valores))
    auditoria_service.registrar(db, tenant_id, "whatsapp_direct_send_alterado", "configuracao_whatsapp", existente.id, ator_id, {"habilitado": habilitado})
    db.commit()
