from fastapi import APIRouter, Depends
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.api.deps import exigir_papel, get_ator_id, get_db, get_tenant_id, resolver_whatsapp_provider
from app.models.configuracao_whatsapp import ConfiguracaoWhatsApp
from app.schemas.configuracao_whatsapp import (
    ConectarMetaRequestSchema,
    ConfiguracaoWhatsAppSchema,
    ConfiguracaoWhatsAppUpsertSchema,
    DefinirDirectSendRequestSchema,
)
from app.services import auditoria_service, tenant_service, whatsapp_conexao_service
from app.services.errors import ValidacaoFalhou

router = APIRouter(prefix="/configuracao-whatsapp", tags=["configuracao-whatsapp"])


def _para_schema(config: ConfiguracaoWhatsApp) -> ConfiguracaoWhatsAppSchema:
    sufixo = config.access_token[-4:] if len(config.access_token) >= 4 else config.access_token
    return ConfiguracaoWhatsAppSchema(
        id=config.id,
        tenant_id=config.tenant_id,
        phone_number_id=config.phone_number_id,
        business_account_id=config.business_account_id,
        access_token_mascarado=f"••••{sufixo}",
        origem_conexao=config.origem_conexao,
        numero_exibicao=config.numero_exibicao,
        nome_verificado=config.nome_verificado,
        qualidade=config.qualidade,
        direct_send_habilitado=bool(config.direct_send_habilitado),
        direct_send_motivo_desligado=config.direct_send_motivo_desligado,
        criado_em=config.criado_em,
        atualizado_em=config.atualizado_em,
    )


@router.get("", response_model=ConfiguracaoWhatsAppSchema | None, dependencies=[Depends(exigir_papel("super_admin", "admin"))])
def obter_configuracao_whatsapp(
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> ConfiguracaoWhatsAppSchema | None:
    config = db.query(ConfiguracaoWhatsApp).filter_by(tenant_id=tenant_id).one_or_none()
    return _para_schema(config) if config else None


@router.put("", response_model=ConfiguracaoWhatsAppSchema, dependencies=[Depends(exigir_papel("super_admin", "admin"))])
def salvar_configuracao_whatsapp(
    dados: ConfiguracaoWhatsAppUpsertSchema,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
) -> ConfiguracaoWhatsAppSchema:
    """Credenciais Meta próprias do tenant — nunca devolve o
    access_token em texto puro depois de salvo (só o sufixo mascarado),
    então numa edição posterior sem trocar o token, `access_token` vem
    vazio e mantemos o valor já salvo.

    Checagem de existência e escrita passam por `select`/`update` de
    baixo nível, nunca carregando a entidade ORM inteira (raio-X
    2026-08-27): se o token já salvo foi cifrado com uma chave de
    criptografia diferente da atual (ex.: chave rotacionada depois do
    token), um `db.query(ConfiguracaoWhatsApp)...one_or_none()` comum já
    decifra `access_token` na hora de montar a linha e estoura
    `cryptography.fernet.InvalidToken` — mesmo numa edição que ia
    sobrescrever o token quebrado por um novo válido, a pessoa nunca
    conseguia corrigir isso pela tela (nem `defer()` evita: o
    `TypeDecorator` roda no result-set inteiro antes do ORM decidir o
    que materializar). Selecionar só as colunas sem tipo criptografado
    evita tocar o valor antigo por completo."""
    linha_existente = db.execute(
        select(ConfiguracaoWhatsApp.id).where(ConfiguracaoWhatsApp.tenant_id == tenant_id)
    ).one_or_none()

    if linha_existente is None:
        if not dados.access_token:
            raise ValidacaoFalhou("Access token é obrigatório na primeira configuração.")
        config = ConfiguracaoWhatsApp(
            tenant_id=tenant_id,
            access_token=dados.access_token,
            phone_number_id=dados.phone_number_id,
            business_account_id=dados.business_account_id,
            origem_conexao="manual",
        )
        db.add(config)
        db.flush()
        config_id = config.id
    else:
        config_id = linha_existente.id
        valores = {"phone_number_id": dados.phone_number_id, "business_account_id": dados.business_account_id, "origem_conexao": "manual"}
        if dados.access_token:
            valores["access_token"] = dados.access_token
        db.execute(update(ConfiguracaoWhatsApp).where(ConfiguracaoWhatsApp.id == config_id).values(**valores))

    auditoria_service.registrar(
        db, tenant_id, "configuracao_whatsapp_salva", "configuracao_whatsapp", config_id, ator_id, {}
    )
    db.commit()
    config = db.get(ConfiguracaoWhatsApp, config_id)
    return _para_schema(config)


_SO_ADMIN = [Depends(exigir_papel("super_admin", "admin"))]


@router.get("/conectar-meta/parametros", dependencies=_SO_ADMIN)
def parametros_conexao_meta() -> dict:
    """IDs públicos que o navegador usa para abrir a janela de cadastro da Meta. `disponivel: false` = só configuração manual."""
    return whatsapp_conexao_service.parametros()


@router.post("/conectar-meta", dependencies=_SO_ADMIN)
def conectar_pela_meta(
    dados: ConectarMetaRequestSchema,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
) -> dict:
    """Conclui o cadastro incorporado: troca o código pelo token, inscreve o app, registra o número e devolve o que a Meta mostrou."""
    return whatsapp_conexao_service.conectar(db, tenant_id, ator_id, dados.codigo, dados.phone_number_id, dados.business_account_id)


@router.post("/testar", dependencies=_SO_ADMIN)
def testar_conexao(tenant_id: str = Depends(get_tenant_id), db: Session = Depends(get_db)) -> dict:
    """Pergunta à Meta pelo número configurado (número, nome verificado, qualidade) — mostra na hora se token e IDs funcionam."""
    return whatsapp_conexao_service.testar(db, tenant_id, resolver_whatsapp_provider(tenant_id, db))


@router.put("/direct-send", status_code=204, dependencies=_SO_ADMIN)
def definir_direct_send(
    dados: DefinirDirectSendRequestSchema,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
) -> None:
    """Liga/desliga o envio sem template (Direct Send). Ligue só se o WhatsApp Manager da Meta mostrar a conta como elegível."""
    whatsapp_conexao_service.definir_direct_send(db, tenant_id, ator_id, dados.habilitado)


@router.post("/confirmar-aviso-template", status_code=204)
def confirmar_aviso_template(
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> None:
    """Dispensa em definitivo o aviso de que o WhatsApp precisa de um
    template aprovado pela Meta pra primeiro contato — qualquer usuário
    autenticado do tenant pode confirmar (é só um lembrete, não uma
    credencial)."""
    tenant_service.confirmar_aviso_whatsapp_template(db, tenant_id)
