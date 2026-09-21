from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class RecursosPlanoSchema(BaseModel):
    """Gancho de upgrade além de volume (raio-X 2026-09-09) — a UI usa isso
    pra mostrar o cadeado direto, sem esperar um 403; a checagem de
    verdade sempre acontece de novo no backend em cada rota."""

    ab_teste_cadencia: bool = False
    auto_aprovacao: bool = False
    webhook_relatorio: bool = False
    api_parceiros: bool = False
    subtenants: bool = False
    registro_oportunidade: bool = False
    retencao_dias_relatorio: int | None = None


class UsuarioSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: str
    nome: str
    email: str
    papel: str
    ativo: bool
    criado_em: datetime
    ultimo_login_em: datetime | None
    termos_aceitos_em: datetime | None
    # Tipo do tenant do usuário (distribuidor|revendedor|cliente) — raio-X:
    # hierarquia de distribuidores. Não vem de `Usuario` (from_attributes) —
    # default aqui só permite `model_validate` passar sem o atributo; o
    # valor real é preenchido em `_resposta_token` via query em `Tenant`.
    tenant_tipo: str = "cliente"
    # Mesmo padrão de `tenant_tipo` acima — preenchido em `_resposta_token`
    # a partir do `PlanLimitsProvider`, não vem de `Usuario`.
    recursos_plano: RecursosPlanoSchema = RecursosPlanoSchema()
    # Idem — vem de `Tenant.aviso_whatsapp_template_confirmado`, não de
    # `Usuario` (raio-X 2026-09-14: aviso de template do WhatsApp).
    aviso_whatsapp_template_confirmado: bool = False
    # Raio-X 2026-09-15: número pessoal do próprio vendedor, cadastrado em
    # "Meu Perfil" — vem direto de `Usuario.whatsapp_pessoal`.
    whatsapp_pessoal: str | None = None
    # Idem — computado em `_resposta_token` (não vem de `Usuario`): se
    # existe pelo menos uma `Conta` com `vendedor_usuario_id` igual ao
    # deste usuário. Liga o aviso proativo de WhatsApp pessoal faltando —
    # sem isso, um vendedor sem conta nenhuma atribuída seria incomodado
    # à toa (raio-X 2026-09-15).
    tem_conta_atribuida: bool = False
    # Redesign Salesforce (raio-X 2026-09-21): vem direto de
    # `Usuario.boas_vindas_banner_dispensado` (from_attributes) — dispensa
    # em definitivo o banner de atalhos da Dashboard.
    boas_vindas_banner_dispensado: bool = False
    # Tutorial por módulo (raio-X 2026-09-21) — lista de chaves de módulo
    # já vistas; vem de `Usuario.tutoriais_modulo_vistos`, que é nullable
    # no banco (nulo = nenhum módulo visto ainda) — frontend trata `null`
    # com `?? []` antes de checar `.includes(...)`.
    tutoriais_modulo_vistos: list[str] | None = None


class LoginRequestSchema(BaseModel):
    email: EmailStr
    senha: str = Field(min_length=1, max_length=72)


class LoginGoogleRequestSchema(BaseModel):
    id_token: str


class RegistrarRequestSchema(BaseModel):
    codigo_convite: str
    nome: str
    email: EmailStr
    senha: str = Field(min_length=8, max_length=72)
    aceite_termos: bool


class RegistrarVitrineRequestSchema(BaseModel):
    codigo_convite: str
    razao_social: str
    cnpj: str | None = None
    nome_admin: str
    email_admin: EmailStr
    senha_admin: str = Field(min_length=8, max_length=72)
    aceite_termos: bool
    # None quando o convite é gratuito (o servidor decide o plano
    # sozinho, ignorando qualquer plano_id enviado — ver
    # tenant_service.criar_tenant_vitrine).
    plano_id: int | None = None


class RegistrarPublicoRequestSchema(BaseModel):
    """Cadastro público sem convite (raio-X 2026-09-21, página de
    boas-vindas) — `plano_id` é obrigatório aqui (sem convite não há
    plano padrão pra cair de volta); o plano Teste nunca é aceito
    (validado em `tenant_service.criar_tenant_publico`)."""

    razao_social: str
    cnpj: str | None = None
    nome_admin: str
    email_admin: EmailStr
    senha_admin: str = Field(min_length=8, max_length=72)
    aceite_termos: bool
    plano_id: int


class TokenResponseSchema(BaseModel):
    access_token: str
    token_type: str = "bearer"
    usuario: UsuarioSchema
    tem_licenca_ativa: bool = True
    checkout_url: str | None = None
    # True só no primeiro login de verdade (ou cadastro novo) — dispara o
    # tour guiado de onboarding no frontend uma única vez.
    primeiro_login: bool = False


class LicencaStatusResponseSchema(BaseModel):
    status: str


class AtualizarWhatsappPessoalRequestSchema(BaseModel):
    whatsapp_pessoal: str | None = None


class MarcarTutorialModuloVistoRequestSchema(BaseModel):
    modulo: str


class EsqueciSenhaRequestSchema(BaseModel):
    email: EmailStr


class RedefinirSenhaRequestSchema(BaseModel):
    token: str
    nova_senha: str = Field(min_length=8, max_length=72)


class RespostaMensagemSchema(BaseModel):
    mensagem: str
