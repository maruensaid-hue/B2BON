import logging
import re
import secrets
import unicodedata
from datetime import UTC, datetime, timedelta

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.base import Base
from app.graph.client import Neo4jClient
from app.integrations.site_fetcher import SiteFetcher
from app.llm.base import LLMProvider
from app.models.auditoria import AuditLog
from app.models.chave_api_parceiro import ChaveApiParceiro
from app.models.convite_vitrine import ConviteVitrine
from app.models.licenca import Licenca
from app.models.plano import Plano
from app.models.tenant import Tenant
from app.models.usuario import Usuario
from app.providers.account_data.base import AccountDataProvider
from app.providers.channels.email.base import EmailProvider
from app.providers.contact_enrichment.base import ContactEnrichmentProvider
from app.providers.payment.base import PaymentProvider
from app.providers.web_search.base import WebSearchProvider
from app.services import (
    auditoria_service,
    auth_service,
    conta_service,
    pagamento_licenca_service,
    rede_social_service,
    webhook_parceiro_service,
)
from app.services.errors import NaoAutorizado, NaoEncontrado, RegraNegocioViolada, ValidacaoFalhou

logger = logging.getLogger(__name__)

# Hierarquia de tenants (raio-X: fundação pra API de provisionamento/billing
# dos distribuidores). "distribuidor" só existe direto sob a CyberFort (sem
# pai); "revendedor" exige pai "distribuidor"; "cliente" pode ter pai
# "revendedor"/"distribuidor" ou nenhum (caso de todo tenant já existente,
# cliente direto da CyberFort sem revenda).
TIPOS_TENANT_VALIDOS = {"distribuidor", "revendedor", "cliente"}
MODOS_COBRANCA_VALIDOS = {"direta", "consolidada"}
_PROFUNDIDADE_MAXIMA_HIERARQUIA = 5


def listar_planos(db: Session, apenas_self_service: bool = False) -> list[Plano]:
    """`apenas_self_service=True` esconde planos como "Teste" — só podem
    ser concedidos por convite gratuito administrativo, nunca escolhidos
    livremente em `POST /auth/registrar-vitrine` (raio-X: mesmo filtro é
    reforçado no servidor em `criar_tenant_vitrine`, não só aqui — a
    listagem sozinha não impede alguém de mandar o `plano_id` direto)."""
    query = db.query(Plano)
    if apenas_self_service:
        query = query.filter_by(visivel_self_service=True)
    return query.order_by(Plano.preco_mensal).all()


def _obter_plano_teste(db: Session) -> Plano:
    plano = db.query(Plano).filter_by(nome="Teste").one_or_none()
    if plano is None:
        raise RegraNegocioViolada(
            "Plano \"Teste\" não encontrado — crie-o antes de gerar convites gratuitos."
        )
    return plano


def _validar_hierarquia(db: Session, tipo: str, tenant_pai_id: str | None, modo_cobranca: str) -> None:
    if tipo not in TIPOS_TENANT_VALIDOS:
        raise ValidacaoFalhou(f"tipo inválido: {tipo!r}. Use um de {sorted(TIPOS_TENANT_VALIDOS)}.")
    if modo_cobranca not in MODOS_COBRANCA_VALIDOS:
        raise ValidacaoFalhou(f"modo_cobranca inválido: {modo_cobranca!r}. Use um de {sorted(MODOS_COBRANCA_VALIDOS)}.")

    if tipo == "distribuidor":
        if tenant_pai_id is not None:
            raise RegraNegocioViolada("Um distribuidor não pode ter tenant pai — fica direto sob a CyberFort.")
        return

    if tenant_pai_id is None:
        if tipo == "revendedor":
            raise RegraNegocioViolada("Um revendedor precisa de um distribuidor pai.")
        return  # tipo == "cliente" sem pai: cliente direto da CyberFort, sem revenda.

    pai = db.query(Tenant).filter_by(id=tenant_pai_id).one_or_none()
    if pai is None:
        raise NaoEncontrado(f"Tenant pai {tenant_pai_id} não encontrado.")
    if tipo == "revendedor" and pai.tipo != "distribuidor":
        raise RegraNegocioViolada("O pai de um revendedor precisa ser um distribuidor.")
    if tipo == "cliente" and pai.tipo not in {"revendedor", "distribuidor"}:
        raise RegraNegocioViolada("O pai de um cliente precisa ser um revendedor ou distribuidor.")


def criar_tenant_inicial(
    db: Session,
    tenant_id: str,
    razao_social: str,
    plano_id: int,
    nome_admin: str,
    email_admin: str,
    senha_admin: str,
    cnpj: str | None = None,
    tenant_pai_id: str | None = None,
    tipo: str = "cliente",
    modo_cobranca: str = "direta",
    papel_primeiro_usuario: str = "super_admin",
    email_provider: EmailProvider | None = None,
) -> Usuario:
    """Cria Tenant + Licença ativa + primeiro usuário.

    `papel_primeiro_usuario` default `"super_admin"` preserva o bootstrap
    original (`scripts/bootstrap_tenant.py`, que não passa esse argumento).
    A rota HTTP (`POST /admin/tenants`) sempre passa `"admin"` explicitamente
    — com a hierarquia, deixar essa rota mintar novos `super_admin` livremente
    quebraria o isolamento (qualquer Distribuidor/Revendedor ganharia acesso
    cross-*toda* a plataforma, não só à própria árvore).
    """
    _validar_hierarquia(db, tipo, tenant_pai_id, modo_cobranca)
    if db.query(Tenant).filter_by(id=tenant_id).one_or_none() is not None:
        raise RegraNegocioViolada(f"Tenant {tenant_id} já existe.")
    if db.query(Plano).filter_by(id=plano_id).one_or_none() is None:
        raise NaoEncontrado(f"Plano {plano_id} não encontrado")
    if db.query(Usuario).filter_by(email=email_admin).one_or_none() is not None:
        raise RegraNegocioViolada("E-mail já cadastrado.")

    tenant = Tenant(
        id=tenant_id,
        razao_social=razao_social,
        cnpj=cnpj,
        tenant_pai_id=tenant_pai_id,
        tipo=tipo,
        modo_cobranca=modo_cobranca,
    )
    db.add(tenant)
    db.flush()

    licenca = Licenca(tenant_id=tenant.id, plano_id=plano_id, status="ativa")
    db.add(licenca)

    rede_social_service.criar_perfil_inicial(db, tenant.id, razao_social)

    usuario = Usuario(
        tenant_id=tenant.id,
        nome=nome_admin,
        email=email_admin,
        senha_hash=auth_service.hash_senha(senha_admin),
        papel=papel_primeiro_usuario,
    )
    db.add(usuario)
    db.flush()

    auditoria_service.registrar(
        db, tenant.id, "tenant_criado", "tenant", 0, None, {"razao_social": razao_social}
    )
    if tenant_pai_id is not None:
        webhook_parceiro_service.enfileirar_evento(
            db, tenant.id, "tenant_provisionado",
            {"tenant_id": tenant.id, "razao_social": razao_social, "tipo": tipo, "tenant_pai_id": tenant_pai_id, "plano_id": plano_id},
        )
    db.commit()
    db.refresh(usuario)

    # Best-effort: e-mail de boas-vindas não pode travar a criação do
    # tenant (mesmo espírito de `sincronizar_com_tolerancia`) — se o
    # provedor falhar, só loga; a conta já existe e já pode ser usada
    # mesmo sem o e-mail chegar.
    if email_provider is not None:
        try:
            corpo = (
                f"Olá, {nome_admin}!\n\n"
                f"Sua conta na B2B ON está pronta — {razao_social} já tem acesso ao CRM, "
                f"prospecção automatizada e MAP (Motor de Alta Performance).\n\n"
                f"Acesse com seu e-mail cadastrado ({email_admin}) em:\n"
                f"{settings.url_base_frontend}/login"
            )
            email_provider.enviar(
                email_admin, "Sua conta na B2B ON está pronta", corpo, "B2B ON",
                settings.sendgrid_remetente_email, tenant.id,
            )
        except Exception:
            logger.warning("Falha ao enviar e-mail de boas-vindas pro tenant %s", tenant.id, exc_info=True)

    return usuario


def listar_tenants(db: Session) -> list[Tenant]:
    """Visão cross-tenant sem escopo — só para super_admin (Onda A)."""
    return db.query(Tenant).order_by(Tenant.id).all()


def e_ancestral(db: Session, possivel_ancestral_id: str, tenant_id: str) -> bool:
    """Sobe a cadeia de `tenant_pai_id` a partir de `tenant_id` até achar
    `possivel_ancestral_id` ou chegar ao topo da árvore. Teto de
    profundidade evita loop infinito em caso de dado corrompido (ciclo) —
    a hierarquia é rasa por design (3 níveis sob a CyberFort). Compartilhado
    entre `deps.exigir_gestor_do_tenant` (JWT) e a API de parceiros (chave
    de API, Fase 2 da hierarquia)."""
    atual = db.query(Tenant).filter_by(id=tenant_id).one_or_none()
    for _ in range(_PROFUNDIDADE_MAXIMA_HIERARQUIA):
        if atual is None or atual.tenant_pai_id is None:
            return False
        if atual.tenant_pai_id == possivel_ancestral_id:
            return True
        atual = db.query(Tenant).filter_by(id=atual.tenant_pai_id).one_or_none()
    return False


def listar_subarvore(db: Session, tenant_id_raiz: str) -> list[Tenant]:
    """`tenant_id_raiz` + toda a subárvore abaixo dele (BFS limitado em
    profundidade — a hierarquia é rasa por design, 3 níveis sob a
    CyberFort). Compartilhado entre `listar_tenants_visiveis` (chamador
    humano, JWT) e a API de parceiros (chamador de máquina, chave de API,
    Fase 2 da hierarquia) — nenhum dos dois tem noção de super_admin aqui,
    isso é decidido por quem chama."""
    visiveis = [tenant_id_raiz]
    fronteira = [tenant_id_raiz]
    for _ in range(_PROFUNDIDADE_MAXIMA_HIERARQUIA):
        filhos = db.query(Tenant).filter(Tenant.tenant_pai_id.in_(fronteira)).all()
        if not filhos:
            break
        fronteira = [filho.id for filho in filhos]
        visiveis.extend(fronteira)

    return db.query(Tenant).filter(Tenant.id.in_(visiveis)).order_by(Tenant.id).all()


def listar_tenants_visiveis(db: Session, usuario: Usuario) -> list[Tenant]:
    """super_admin enxerga tudo; admin de um tenant distribuidor/revendedor
    enxerga o próprio tenant + toda a subárvore abaixo dele. Admin de um
    tenant "cliente" (folha) só enxerga a si mesmo."""
    if usuario.papel == "super_admin":
        return listar_tenants(db)
    return listar_subarvore(db, usuario.tenant_id)


def suspender_licencas_vencidas(db: Session) -> list[str]:
    """Suspensão automática por inadimplência (raio-X) — antes disso,
    `data_expiracao` nunca era comparado com a data atual em lugar nenhum
    do código; uma licença vencida continuava dando acesso total até um
    humano mudar o status manualmente. Só afeta tenants `modo_cobranca ==
    "direta"` — um tenant "consolidada" não tem `data_expiracao` própria
    relevante, o status de pagamento vem do tenant pai (ver
    `exigir_licenca_ativa`)."""
    agora = datetime.now(UTC)
    licencas_vencidas = (
        db.query(Licenca)
        .join(Tenant, Tenant.id == Licenca.tenant_id)
        .filter(
            Licenca.status == "ativa",
            Licenca.data_expiracao.isnot(None),
            Licenca.data_expiracao < agora,
            Tenant.modo_cobranca == "direta",
        )
        .all()
    )

    tenants_suspensos = []
    for licenca in licencas_vencidas:
        licenca.status = "suspensa"
        auditoria_service.registrar(
            db, licenca.tenant_id, "licenca_suspensa_automaticamente", "licenca", licenca.id, None,
            {"data_expiracao": licenca.data_expiracao.isoformat()},
        )
        webhook_parceiro_service.enfileirar_evento(
            db, licenca.tenant_id, "licenca_suspensa",
            {"tenant_id": licenca.tenant_id, "data_expiracao": licenca.data_expiracao.isoformat()},
        )
        tenants_suspensos.append(licenca.tenant_id)

    db.commit()
    return tenants_suspensos


def obter_licenca(db: Session, tenant_id: str) -> Licenca:
    licenca = db.query(Licenca).filter_by(tenant_id=tenant_id).one_or_none()
    if licenca is None:
        raise NaoEncontrado(f"Licença do tenant {tenant_id} não encontrada")
    return licenca


def atualizar_licenca(
    db: Session,
    tenant_id: str,
    ator_id: str | None,
    plano_id: int | None,
    status: str | None,
    data_expiracao: datetime | None,
) -> Licenca:
    """Cria a licença se o tenant ainda não tiver nenhuma (ex.: tenant
    nascido de convite-vitrine, sem `Licenca` por design — Onda H) ou
    atualiza a existente. Sem isso, não havia como transformar um tenant
    vitrine em cliente pagante pela tela de Admin: `obter_licenca`
    recusava qualquer tenant sem licença, mesmo para criar a primeira."""
    licenca = db.query(Licenca).filter_by(tenant_id=tenant_id).one_or_none()

    if licenca is None:
        if db.query(Tenant).filter_by(id=tenant_id).one_or_none() is None:
            raise NaoEncontrado(f"Tenant {tenant_id} não encontrado")
        if plano_id is None:
            raise RegraNegocioViolada("Escolha um plano para criar a primeira licença deste tenant.")
        if db.query(Plano).filter_by(id=plano_id).one_or_none() is None:
            raise NaoEncontrado(f"Plano {plano_id} não encontrado")
        licenca = Licenca(
            tenant_id=tenant_id, plano_id=plano_id, status=status or "ativa", data_expiracao=data_expiracao
        )
        db.add(licenca)
        db.flush()
        auditoria_service.registrar(
            db, tenant_id, "licenca_criada", "licenca", licenca.id, ator_id, {"plano_id": plano_id, "status": licenca.status}
        )
        webhook_parceiro_service.enfileirar_evento(
            db, tenant_id, "licenca_atualizada", {"tenant_id": tenant_id, "plano_id": plano_id, "status": licenca.status}
        )
        db.commit()
        db.refresh(licenca)
        return licenca

    if plano_id is not None:
        if db.query(Plano).filter_by(id=plano_id).one_or_none() is None:
            raise NaoEncontrado(f"Plano {plano_id} não encontrado")
        licenca.plano_id = plano_id
    if status is not None:
        licenca.status = status
    if data_expiracao is not None:
        licenca.data_expiracao = data_expiracao

    auditoria_service.registrar(
        db,
        tenant_id,
        "licenca_atualizada",
        "licenca",
        licenca.id,
        ator_id,
        {"plano_id": plano_id, "status": status},
    )
    webhook_parceiro_service.enfileirar_evento(
        db, tenant_id, "licenca_atualizada", {"tenant_id": tenant_id, "plano_id": licenca.plano_id, "status": licenca.status}
    )
    db.commit()
    db.refresh(licenca)
    return licenca


def _obter_tenant(db: Session, tenant_id: str) -> Tenant:
    tenant = db.query(Tenant).filter_by(id=tenant_id).one_or_none()
    if tenant is None:
        raise NaoEncontrado(f"Tenant {tenant_id} não encontrado")
    return tenant


def _tem_filho(db: Session, tenant_id: str) -> bool:
    """`tenant_pai_id` só aponta pro pai imediato — "sem filho direto" já
    implica "sem descendente nenhum" (não precisa varrer a árvore)."""
    return db.query(Tenant).filter_by(tenant_pai_id=tenant_id).first() is not None


def desativar(db: Session, tenant_id: str, ator: Usuario) -> Tenant:
    """Desativação reversível: bloqueia login e API de parceiro sem apagar
    nada. Reaproveita a checagem `usuario.ativo` que `auth_service.
    autenticar_senha`/`autenticar_google`/`validar_token` já fazem — não
    precisa de nenhuma mudança nesses três lugares."""
    tenant = _obter_tenant(db, tenant_id)
    if not tenant.ativo:
        raise RegraNegocioViolada(f'Tenant "{tenant_id}" já está desativado.')
    if _tem_filho(db, tenant_id):
        raise RegraNegocioViolada("Existem tenants abaixo deste — desative-os antes de desativar este.")

    tenant.ativo = False

    usuarios_ativos_antes = [
        usuario_id for (usuario_id,) in db.query(Usuario.id).filter_by(tenant_id=tenant_id, ativo=True).all()
    ]
    db.query(Usuario).filter_by(tenant_id=tenant_id, ativo=True).update({"ativo": False})

    # `get_chave_api_atual` (app/api/deps.py) já filtra por `revogada_em is
    # None` — revogar aqui reaproveita essa checagem, sem tocar na
    # dependency: sem isso, um Distribuidor desativado continuaria
    # provisionando tenants via /parceiros/* com a chave antiga.
    db.query(ChaveApiParceiro).filter_by(tenant_id=tenant_id, revogada_em=None).update(
        {"revogada_em": datetime.now(UTC)}
    )

    auditoria_service.registrar(
        db, tenant_id, "tenant_desativado", "tenant", 0, str(ator.id), {"usuarios_reativar": usuarios_ativos_antes}
    )
    db.commit()
    db.refresh(tenant)
    return tenant


def reativar(db: Session, tenant_id: str, ator: Usuario) -> Tenant:
    """Reverte `desativar` — só religa os usuários que estavam ativos
    IMEDIATAMENTE antes da desativação (lista salva no audit log), pra não
    ressuscitar alguém que já tinha sido desativado por outro motivo antes
    disso. Chave de API de parceiro não volta sozinha — reemitir é ação
    separada, mais sensível, feita pela tela de Integrações."""
    tenant = _obter_tenant(db, tenant_id)
    if tenant.ativo:
        raise RegraNegocioViolada(f'Tenant "{tenant_id}" já está ativo.')

    tenant.ativo = True

    ultimo_evento = (
        db.query(AuditLog)
        .filter_by(tenant_id=tenant_id, evento_tipo="tenant_desativado")
        .order_by(AuditLog.id.desc())
        .first()
    )
    ids_para_reativar = ultimo_evento.detalhes.get("usuarios_reativar", []) if ultimo_evento else []
    if ids_para_reativar:
        db.query(Usuario).filter(Usuario.id.in_(ids_para_reativar)).update(
            {"ativo": True}, synchronize_session=False
        )

    auditoria_service.registrar(db, tenant_id, "tenant_reativado", "tenant", 0, str(ator.id), {})
    db.commit()
    db.refresh(tenant)
    return tenant


# Tabelas que pertencem a um tenant só indiretamente (sem `tenant_id`
# próprio) — mesmo gotcha de `CampoEnriquecido` já tratado em
# `conta_service.excluir`. Sem isto, `excluir_definitivamente` deixaria
# essas linhas órfãs (ou, pior, com FK real, bloquearia a exclusão da
# tabela-pai com erro de integridade).
def _condicoes_indiretas(metadata):
    conta = metadata.tables["conta"]
    assinatura = metadata.tables["assinatura_webhook_parceiro"]
    return {
        "campo_enriquecido": lambda t, tenant_id: t.c.conta_id.in_(
            select(conta.c.id).where(conta.c.tenant_id == tenant_id)
        ),
        "evento_webhook_parceiro": lambda t, tenant_id: t.c.assinatura_id.in_(
            select(assinatura.c.id).where(assinatura.c.tenant_id == tenant_id)
        ),
    }


# Tabelas que TÊM `tenant_id`, mas ficam fora da varredura por razão
# semântica/legal (não estrutural — não dá pra confiar só em "sem
# tenant_id = pode ignorar" aqui):
# - "plano": catálogo global, não é dado do tenant.
# - "recorte_cnpj_estado": cache global de shard de CNPJ (não tem
#   tenant_id de qualquer forma, listado aqui só por clareza).
# - "registro_tratamento": ROPA/LGPD sobre o módulo, não por tenant.
# - "registro_supressao_permanente": existe justamente PRA sobreviver a
#   qualquer exclusão — apaga o PII, mantém a prova de opt-out, senão a
#   garantia de "nunca mais recontatar" desaparece junto com o tenant.
# - "pagamento_licenca": histórico de pagamento retido por obrigação
#   fiscal/contábil (decisão confirmada com o usuário), mesmo com o
#   tenant já apagado.
_TABELAS_EXCLUIDAS_DA_VARREDURA = {
    "tenant",
    "plano",
    "recorte_cnpj_estado",
    "registro_tratamento",
    "registro_supressao_permanente",
    "pagamento_licenca",
}


def excluir_definitivamente(db: Session, tenant_id: str, ator: Usuario) -> None:
    """Exclusão definitiva: varre TODO o schema (não uma lista de tabelas
    escrita à mão) via `Base.metadata.sorted_tables` — ordenação
    topológica automática do SQLAlchemy, que já considera todas as FKs do
    schema (não só as que apontam pro tenant), em ordem reversa (filhos
    antes dos pais). Nenhuma tabela tem `ondelete="CASCADE"` (tudo é
    RESTRICT por padrão do Postgres) — se a varredura esquecer alguma
    tabela, o DELETE da tabela-pai estoura `IntegrityError` em vez de
    deixar dado órfão silenciosamente (rede de segurança "falha fechado").

    Commit por tabela, não uma transação gigante única — mesmo raciocínio
    de `conta_service._excluir_contas_em_lote` (documentado ali: exclusão
    em lote sem chunking já estourou timeout de request com 6200 linhas;
    um tenant inteiro pode ter volume bem maior). Isso também torna a
    operação idempotente: se cair no meio, rodar de novo só continua de
    onde parou."""
    tenant = _obter_tenant(db, tenant_id)
    if ator.papel == "admin" and ator.tenant_id == tenant_id:
        raise NaoAutorizado("Você não pode excluir definitivamente o próprio tenant — peça a um gestor acima.")
    if _tem_filho(db, tenant_id):
        raise RegraNegocioViolada("Existem tenants abaixo deste — remova-os antes de excluir definitivamente.")

    metadata = Base.metadata
    condicoes_indiretas = _condicoes_indiretas(metadata)

    for table in reversed(metadata.sorted_tables):
        if table.name in _TABELAS_EXCLUIDAS_DA_VARREDURA:
            continue
        if table.name in condicoes_indiretas:
            db.execute(table.delete().where(condicoes_indiretas[table.name](table, tenant_id)))
            db.commit()
            continue
        colunas_tenant = [coluna for coluna in table.columns if coluna.name.startswith("tenant_id")]
        if not colunas_tenant:
            continue
        db.execute(table.delete().where(or_(*(coluna == tenant_id for coluna in colunas_tenant))))
        db.commit()

    # Log sob o tenant de quem executou, não o que está sumindo — senão o
    # próprio registro da exclusão desapareceria junto (admin nunca exclui
    # o próprio tenant, ver checagem acima, então `ator.tenant_id` nunca é
    # o tenant que acabou de sumir).
    auditoria_service.registrar(
        db, ator.tenant_id, "tenant_excluido_definitivamente", "tenant", 0, str(ator.id),
        {"tenant_id": tenant_id, "razao_social": tenant.razao_social},
    )
    db.delete(tenant)
    db.commit()


def _gerar_tenant_id(db: Session, razao_social: str) -> str:
    """Slug legível a partir da razão social — o convite-vitrine não pede
    o identificador do tenant ao usuário final, então é gerado aqui, com
    sufixo aleatório em caso de colisão (Onda H)."""
    sem_acentos = unicodedata.normalize("NFKD", razao_social).encode("ascii", "ignore").decode("ascii")
    base = re.sub(r"[^a-z0-9]+", "-", sem_acentos.lower()).strip("-")[:40] or "empresa"
    candidato = base
    while db.query(Tenant).filter_by(id=candidato).one_or_none() is not None:
        candidato = f"{base}-{secrets.token_hex(3)}"
    return candidato


def gerar_convite_vitrine(
    db: Session,
    tenant_id_origem: str,
    ator_id: str | None,
    validade_horas: int | None,
    email_destinatario: str | None = None,
    email_provider: EmailProvider | None = None,
    gratuito: bool = False,
) -> ConviteVitrine:
    """Qualquer usuário de um tenant já existente pode convidar uma
    empresa nova para a Rede Social (Onda H) — não exige papel admin,
    diferente do convite de usuário (`auth_service.gerar_convite`).
    `gratuito=True` é a exceção: a rota (`app/api/v1/convites.py`) só
    permite isso pra admin/super_admin — vira Licença "Teste" ativa sem
    prazo de expiração, sem passar pelo checkout (raio-X).

    Antes disto, o único jeito de "enviar" o convite era copiar o link
    manualmente (nada era enviado de verdade) — bug real relatado pelo
    usuário. Com `email_destinatario` + `email_provider`, o e-mail sai na
    hora; sem eles, continua funcionando como antes (só copiar o link)."""
    validade_em = datetime.now(UTC) + timedelta(hours=validade_horas) if validade_horas else None
    convite = ConviteVitrine(
        tenant_id_origem=tenant_id_origem,
        codigo=secrets.token_hex(8).upper(),
        criado_por_usuario_id=int(ator_id) if ator_id else None,
        validade_em=validade_em,
        gratuito=gratuito,
    )
    db.add(convite)
    db.flush()

    auditoria_service.registrar(
        db, tenant_id_origem, "convite_vitrine_gerado", "convite_vitrine", convite.id, ator_id, {}
    )
    db.commit()
    db.refresh(convite)

    # Atributo dinâmico (não é coluna do modelo) — só pra carregar o
    # resultado do envio até a resposta da rota (`ConviteVitrineCriadoSchema`).
    # `StubEmailProvider` sempre reportava sucesso mesmo sem enviar nada
    # de verdade, então sem checar `resultado.sucesso` aqui o convite
    # parecia enviado quando não saía nada (raio-X de produção real).
    convite.email_enviado = None  # type: ignore[attr-defined]
    if email_destinatario and email_provider is not None:
        tenant_origem = db.query(Tenant).filter_by(id=tenant_id_origem).one_or_none()
        nome_origem = tenant_origem.razao_social if tenant_origem else "Um parceiro"
        link = f"{settings.url_base_frontend}/convite-vitrine/{convite.codigo}"
        corpo = (
            f"{nome_origem} te convidou para conhecer a B2B ON — CRM, prospecção, rede social entre "
            f"empresas e MAP (Motor de Alta Performance), tudo numa plataforma só.\n\n"
            f"Para criar sua conta e escolher um plano, acesse:\n{link}\n\n"
            f"Este link expira {'em ' + str(validade_horas) + ' horas' if validade_horas else 'sem prazo definido'}."
        )
        resultado = email_provider.enviar(
            email_destinatario,
            "Você foi convidado para a B2B ON",
            corpo,
            "B2B ON",
            settings.sendgrid_remetente_email,
            tenant_id_origem,
        )
        convite.email_enviado = resultado.sucesso  # type: ignore[attr-defined]

    return convite


def revogar_convite_vitrine(db: Session, tenant_id_origem: str, ator_id: str | None, codigo: str) -> ConviteVitrine:
    convite = db.query(ConviteVitrine).filter_by(tenant_id_origem=tenant_id_origem, codigo=codigo).one_or_none()
    if convite is None:
        raise NaoEncontrado(f"Convite {codigo} não encontrado")
    if convite.status != "disponivel":
        raise RegraNegocioViolada("Só é possível revogar convites disponíveis.")

    convite.status = "revogado"
    auditoria_service.registrar(
        db, tenant_id_origem, "convite_vitrine_revogado", "convite_vitrine", convite.id, ator_id, {}
    )
    db.commit()
    db.refresh(convite)
    return convite


def reativar_convite_vitrine(db: Session, tenant_id_origem: str, ator_id: str | None, codigo: str) -> ConviteVitrine:
    """Volta um convite revogado por engano pra "disponivel" — sem isto,
    revogar por engano ou mudar de ideia obrigava gerar um convite novo
    pra mesma empresa (pedido do usuário: evitar acumular convites)."""
    convite = db.query(ConviteVitrine).filter_by(tenant_id_origem=tenant_id_origem, codigo=codigo).one_or_none()
    if convite is None:
        raise NaoEncontrado(f"Convite {codigo} não encontrado")
    if convite.status != "revogado":
        raise RegraNegocioViolada("Só é possível reativar convites revogados.")

    convite.status = "disponivel"
    auditoria_service.registrar(
        db, tenant_id_origem, "convite_vitrine_reativado", "convite_vitrine", convite.id, ator_id, {}
    )
    db.commit()
    db.refresh(convite)
    return convite


def excluir_convite_vitrine(db: Session, tenant_id_origem: str, ator_id: str | None, codigo: str) -> None:
    """Remove um convite revogado da lista — só revogados, pra nunca
    apagar um convite que alguém ainda possa usar."""
    convite = db.query(ConviteVitrine).filter_by(tenant_id_origem=tenant_id_origem, codigo=codigo).one_or_none()
    if convite is None:
        raise NaoEncontrado(f"Convite {codigo} não encontrado")
    if convite.status != "revogado":
        raise RegraNegocioViolada("Só é possível excluir convites revogados.")

    auditoria_service.registrar(
        db, tenant_id_origem, "convite_vitrine_excluido", "convite_vitrine", convite.id, ator_id, {}
    )
    db.delete(convite)
    db.commit()


def listar_convites_vitrine(db: Session, tenant_id_origem: str) -> list[ConviteVitrine]:
    return (
        db.query(ConviteVitrine)
        .filter_by(tenant_id_origem=tenant_id_origem)
        .order_by(ConviteVitrine.id.desc())
        .all()
    )


def obter_info_convite_vitrine(db: Session, codigo: str) -> ConviteVitrine:
    """Info pública mínima pra tela de cadastro (`ConviteVitrine.tsx`)
    saber, antes de renderizar o formulário, se é um convite gratuito
    (esconde o seletor de plano e a cópia de checkout) ou normal."""
    convite = db.query(ConviteVitrine).filter_by(codigo=codigo).one_or_none()
    if convite is None:
        raise NaoEncontrado(f"Convite {codigo} não encontrado")
    return convite


def _validar_convite_vitrine_disponivel(
    db: Session, convite: ConviteVitrine | None, codigo: str
) -> ConviteVitrine:
    if convite is None:
        raise NaoEncontrado(f"Convite {codigo} não encontrado")
    if convite.status == "revogado":
        raise RegraNegocioViolada("Convite revogado.")
    if convite.status == "usado":
        raise RegraNegocioViolada("Convite já utilizado.")

    validade = convite.validade_em
    if validade is not None:
        if validade.tzinfo is None:
            validade = validade.replace(tzinfo=UTC)
        if validade < datetime.now(UTC):
            convite.status = "expirado"
            db.commit()
            raise RegraNegocioViolada("Convite expirado.")
    return convite


def criar_tenant_vitrine(
    db: Session,
    codigo_convite: str,
    razao_social: str,
    nome_admin: str,
    email_admin: str,
    senha_admin: str,
    aceite_termos: bool,
    plano_id: int | None,
    payment_provider: PaymentProvider,
    llm: LLMProvider,
    site_fetcher: SiteFetcher,
    web_search: WebSearchProvider,
    account_data: AccountDataProvider,
    contact_enrichment: ContactEnrichmentProvider,
    graph: Neo4jClient,
    cnpj: str | None = None,
) -> tuple[Usuario, str | None]:
    """Aceite de convite-vitrine: cria Tenant + Usuario (papel `admin`,
    nunca `super_admin` — isso evitaria acesso a `/admin/tenants`
    cross-tenant) + Perfil de Rede Social + Licença.

    Convite normal (`convite.gratuito=False`): licença nasce
    `pendente_pagamento` do plano escolhido (precisa ser
    `visivel_self_service`) e só vira `ativa` quando o webhook do
    Mercado Pago confirmar (`pagamento_licenca_service`) — até lá o
    tenant fica restrito à Rede Social.

    Convite gratuito (`convite.gratuito=True`, raio-X): `plano_id`
    recebido é **ignorado** — o servidor decide sozinho o plano "Teste",
    nunca confia no que o cliente mandou, porque é exatamente o controle
    que evita alguém contornar o pagamento chamando a rota direto com
    outro `plano_id`. Licença nasce `ativa` sem `data_expiracao`, sem
    checkout nenhum."""
    if not aceite_termos:
        raise ValidacaoFalhou("É preciso aceitar a Política de Privacidade e os Termos de Uso para se cadastrar.")

    convite = db.query(ConviteVitrine).filter_by(codigo=codigo_convite).one_or_none()
    convite = _validar_convite_vitrine_disponivel(db, convite, codigo_convite)

    if convite.gratuito:
        plano_id = _obter_plano_teste(db).id
    else:
        plano = db.query(Plano).filter_by(id=plano_id).one_or_none() if plano_id is not None else None
        if plano is None:
            raise NaoEncontrado(f"Plano {plano_id} não encontrado")
        if not plano.visivel_self_service:
            raise RegraNegocioViolada("Este plano não está disponível para cadastro self-service.")

    if db.query(Usuario).filter_by(email=email_admin).one_or_none() is not None:
        raise RegraNegocioViolada("E-mail já cadastrado.")

    tenant_id = _gerar_tenant_id(db, razao_social)
    # Convite gratuito (raio-X 2026-08-27): tenant cortesia nasce
    # "distribuidor" (raiz da árvore, sem tenant pai), não "cliente" —
    # sem isso, o admin cortesia nunca conseguia criar sub-tenants
    # ("seus próprios clientes"), porque só distribuidor/revendedor
    # passam em `permitir_gestao_hierarquica`. Convite pago continua
    # "cliente" (comportamento inalterado).
    tipo = "distribuidor" if convite.gratuito else "cliente"
    tenant = Tenant(id=tenant_id, razao_social=razao_social, cnpj=cnpj, tipo=tipo)
    db.add(tenant)
    db.flush()

    rede_social_service.criar_perfil_inicial(db, tenant.id, razao_social)

    usuario = Usuario(
        tenant_id=tenant.id,
        nome=nome_admin,
        email=email_admin,
        senha_hash=auth_service.hash_senha(senha_admin),
        papel="admin",
        termos_aceitos_em=datetime.now(UTC),
    )
    db.add(usuario)
    db.flush()

    if convite.gratuito:
        db.add(Licenca(tenant_id=tenant.id, plano_id=plano_id, status="ativa"))
    else:
        db.add(Licenca(tenant_id=tenant.id, plano_id=plano_id, status="pendente_pagamento"))

    convite.status = "usado"
    convite.tenant_id_gerado = tenant.id

    auditoria_service.registrar(
        db,
        tenant.id,
        "tenant_vitrine_criado",
        "tenant",
        0,
        None,
        {"razao_social": razao_social, "convite_codigo": codigo_convite},
    )

    # A empresa convidada também entra como prospect no CRM de quem a
    # convidou — não só como tenant novo e independente da Rede Social.
    conta_prospect = conta_service.criar_a_partir_de_convite_rede_social(
        db, convite.tenant_id_origem, razao_social, cnpj, nome_admin, email_admin
    )

    # Best-effort: a IA já sai pesquisando site e contatos dessa conta
    # recém-criada, mas nada aqui pode travar o cadastro do tenant — se
    # qualquer provedor falhar, só loga e segue (mesmo espírito de
    # `sincronizar_com_tolerancia`).
    try:
        conta_service.enriquecer(
            db, convite.tenant_id_origem, None, conta_prospect.id, llm, site_fetcher, web_search
        )
    except Exception:
        logger.warning("Falha ao enriquecer via site a conta %s criada por convite de rede social", conta_prospect.id, exc_info=True)
    try:
        conta_service.mapear_decisores(
            db, convite.tenant_id_origem, None, conta_prospect.id, account_data, contact_enrichment, graph
        )
    except Exception:
        logger.warning("Falha ao mapear decisores da conta %s criada por convite de rede social", conta_prospect.id, exc_info=True)

    db.commit()
    db.refresh(usuario)

    if convite.gratuito:
        return usuario, None

    _, url_checkout = pagamento_licenca_service.iniciar(db, tenant.id, plano_id, email_admin, payment_provider)
    return usuario, url_checkout
