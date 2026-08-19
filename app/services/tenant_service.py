import logging
import re
import secrets
import unicodedata
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.core.config import settings
from app.graph.client import Neo4jClient
from app.integrations.site_fetcher import SiteFetcher
from app.llm.base import LLMProvider
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
from app.services import auditoria_service, auth_service, conta_service, pagamento_licenca_service, rede_social_service
from app.services.errors import NaoEncontrado, RegraNegocioViolada, ValidacaoFalhou

logger = logging.getLogger(__name__)

# Hierarquia de tenants (raio-X: fundação pra API de provisionamento/billing
# dos distribuidores). "distribuidor" só existe direto sob a CyberFort (sem
# pai); "revendedor" exige pai "distribuidor"; "cliente" pode ter pai
# "revendedor"/"distribuidor" ou nenhum (caso de todo tenant já existente,
# cliente direto da CyberFort sem revenda).
TIPOS_TENANT_VALIDOS = {"distribuidor", "revendedor", "cliente"}
MODOS_COBRANCA_VALIDOS = {"direta", "consolidada"}
_PROFUNDIDADE_MAXIMA_HIERARQUIA = 5


def listar_planos(db: Session) -> list[Plano]:
    return db.query(Plano).order_by(Plano.preco_mensal).all()


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
    db.commit()
    db.refresh(usuario)
    return usuario


def listar_tenants(db: Session) -> list[Tenant]:
    """Visão cross-tenant sem escopo — só para super_admin (Onda A)."""
    return db.query(Tenant).order_by(Tenant.id).all()


def listar_tenants_visiveis(db: Session, usuario: Usuario) -> list[Tenant]:
    """super_admin enxerga tudo; admin de um tenant distribuidor/revendedor
    enxerga o próprio tenant + toda a subárvore abaixo dele (BFS limitado
    em profundidade — a hierarquia é rasa por design, 3 níveis sob a
    CyberFort). Admin de um tenant "cliente" (folha) só enxerga a si mesmo."""
    if usuario.papel == "super_admin":
        return listar_tenants(db)

    visiveis = [usuario.tenant_id]
    fronteira = [usuario.tenant_id]
    for _ in range(_PROFUNDIDADE_MAXIMA_HIERARQUIA):
        filhos = db.query(Tenant).filter(Tenant.tenant_pai_id.in_(fronteira)).all()
        if not filhos:
            break
        fronteira = [filho.id for filho in filhos]
        visiveis.extend(fronteira)

    return db.query(Tenant).filter(Tenant.id.in_(visiveis)).order_by(Tenant.id).all()


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
    db.commit()
    db.refresh(licenca)
    return licenca


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
) -> ConviteVitrine:
    """Qualquer usuário de um tenant já existente pode convidar uma
    empresa nova para a Rede Social (Onda H) — não exige papel admin,
    diferente do convite de usuário (`auth_service.gerar_convite`).

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
    plano_id: int,
    payment_provider: PaymentProvider,
    llm: LLMProvider,
    site_fetcher: SiteFetcher,
    web_search: WebSearchProvider,
    account_data: AccountDataProvider,
    contact_enrichment: ContactEnrichmentProvider,
    graph: Neo4jClient,
    cnpj: str | None = None,
) -> tuple[Usuario, str]:
    """Aceite de convite-vitrine: cria Tenant + Usuario (papel `admin`,
    nunca `super_admin` — isso evitaria acesso a `/admin/tenants`
    cross-tenant) + Perfil de Rede Social + Licença `pendente_pagamento`
    do plano escolhido. A licença só vira `ativa` quando o webhook do
    Mercado Pago confirmar o pagamento (`pagamento_licenca_service`) —
    até lá o tenant fica restrito à Rede Social, igual ao comportamento
    anterior de "vitrine sem licença" (Onda H), só que agora com uma
    cobrança em andamento em vez de ficar assim para sempre."""
    if not aceite_termos:
        raise ValidacaoFalhou("É preciso aceitar a Política de Privacidade e os Termos de Uso para se cadastrar.")

    if db.query(Plano).filter_by(id=plano_id).one_or_none() is None:
        raise NaoEncontrado(f"Plano {plano_id} não encontrado")

    convite = db.query(ConviteVitrine).filter_by(codigo=codigo_convite).one_or_none()
    convite = _validar_convite_vitrine_disponivel(db, convite, codigo_convite)

    if db.query(Usuario).filter_by(email=email_admin).one_or_none() is not None:
        raise RegraNegocioViolada("E-mail já cadastrado.")

    tenant_id = _gerar_tenant_id(db, razao_social)
    tenant = Tenant(id=tenant_id, razao_social=razao_social, cnpj=cnpj)
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

    _, url_checkout = pagamento_licenca_service.iniciar(db, tenant.id, plano_id, email_admin, payment_provider)
    return usuario, url_checkout
