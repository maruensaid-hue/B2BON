"""Conexão do número de WhatsApp de cada empresa: botão "Conectar com a Meta" (cadastro incorporado) e "Testar conexão".

Cada tenant (ou cliente de contratação individual) usa o PRÓPRIO número. No cadastro incorporado a pessoa faz login na Meta numa
janela da própria Meta, escolhe ou cria a conta e o número, e o navegador devolve ao B2B ON um código de uso único e os IDs. Aqui:
1. o código vira o token da empresa (troca feita com o segredo do app, que nunca vai ao navegador);
2. o app é inscrito na conta do WhatsApp (sem isso as respostas dos clientes não chegam ao webhook);
3. o número é registrado na API de nuvem com um PIN novo de 6 dígitos (guardado criptografado);
4. número, nome verificado e qualidade são lidos da Meta e mostrados na tela como prova de que ficou ligado.
O passo 3 pode falhar sem impedir a conexão (número já registrado com outro PIN): fica o aviso com o que fazer.
"""

import secrets

import httpx
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.configuracao_whatsapp import ConfiguracaoWhatsApp
from app.providers.channels.whatsapp.meta import MetaWhatsAppProvider
from app.services import auditoria_service
from app.services.errors import RegraNegocioViolada, ValidacaoFalhou

_TIMEOUT = 20.0


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
    }


def _erro_meta(resposta: httpx.Response) -> str:
    try:
        erro = resposta.json().get("error", {})
    except ValueError:
        erro = {}
    return erro.get("error_user_msg") or erro.get("message") or f"HTTP {resposta.status_code}"


def _trocar_codigo(codigo: str) -> str:
    try:
        resposta = httpx.get(
            f"{_graph()}/oauth/access_token",
            params={"client_id": settings.meta_app_id, "client_secret": settings.whatsapp_app_secret, "code": codigo},
            timeout=_TIMEOUT,
        )
    except httpx.HTTPError as erro:
        raise RegraNegocioViolada(f"A Meta não respondeu ao concluir a conexão ({type(erro).__name__}). Tente de novo.") from erro
    if not resposta.is_success or not resposta.json().get("access_token"):
        raise RegraNegocioViolada(f"A Meta não aceitou concluir a conexão: {_erro_meta(resposta)}. Clique em Conectar de novo.")
    return resposta.json()["access_token"]


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


def _salvar(db: Session, tenant_id: str, valores: dict) -> int:
    existente = db.execute(select(ConfiguracaoWhatsApp.id).where(ConfiguracaoWhatsApp.tenant_id == tenant_id)).one_or_none()
    if existente is None:
        config = ConfiguracaoWhatsApp(tenant_id=tenant_id, **valores)
        db.add(config)
        db.flush()
        return config.id
    db.execute(update(ConfiguracaoWhatsApp).where(ConfiguracaoWhatsApp.id == existente.id).values(**valores))
    return existente.id


def conectar(db: Session, tenant_id: str, ator_id: str | None, codigo: str, phone_number_id: str, waba_id: str) -> dict:
    if not parametros()["disponivel"]:
        raise RegraNegocioViolada("A conexão pela Meta não está disponível nesta instalação: use a configuração manual.")
    if not (codigo and phone_number_id.strip().isdigit() and waba_id.strip().isdigit()):
        raise ValidacaoFalhou("A janela da Meta não devolveu os dados do número. Clique em Conectar e conclua todas as etapas.")
    phone_number_id, waba_id = phone_number_id.strip(), waba_id.strip()

    token = _trocar_codigo(codigo)
    pin = f"{secrets.randbelow(10**6):06d}"
    aviso_registro = _registrar_numero(token, phone_number_id, pin)
    avisos = [a for a in (_inscrever_app(token, waba_id), aviso_registro) if a]
    info = MetaWhatsAppProvider(token, phone_number_id, waba_id).info_numero()

    config_id = _salvar(db, tenant_id, {
        "access_token": token, "phone_number_id": phone_number_id, "business_account_id": waba_id, "origem_conexao": "meta_conectar",
        "pin_registro": pin if aviso_registro is None else None,
        "numero_exibicao": info.numero_exibicao, "nome_verificado": info.nome_verificado, "qualidade": info.qualidade,
    })
    auditoria_service.registrar(db, tenant_id, "whatsapp_conectado_pela_meta", "configuracao_whatsapp", config_id, ator_id,
                                {"avisos": len(avisos), "numero": info.numero_exibicao})
    db.commit()
    return {"numero_exibicao": info.numero_exibicao, "nome_verificado": info.nome_verificado, "qualidade": info.qualidade, "avisos": avisos}


def testar(db: Session, tenant_id: str, provider) -> dict:
    """Pergunta à Meta pelo número configurado e guarda o que ela disse: prova de que token e IDs funcionam."""
    info = provider.info_numero()
    if info.erro is None:
        db.execute(
            update(ConfiguracaoWhatsApp).where(ConfiguracaoWhatsApp.tenant_id == tenant_id)
            .values(numero_exibicao=info.numero_exibicao, nome_verificado=info.nome_verificado, qualidade=info.qualidade)
        )
        db.commit()
    return {"ok": info.erro is None, "numero_exibicao": info.numero_exibicao, "nome_verificado": info.nome_verificado,
            "qualidade": info.qualidade, "erro": info.erro}


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
