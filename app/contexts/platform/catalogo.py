"""Catálogo comercial (Fase 14, Master Prompt §69–§75).

Fonte única do QUE a B2B ON vende e em que estado cada produto está. O
catálogo **não guarda preço**: preço é o `preco_mensal` dos `Plano`s (o
que o checkout cobra). Produto sem plano self-service que o inclua nunca
aparece como disponível para contratação (§72).

Estados de disponibilidade:
- DISPONIVEL: contratável hoje (há plano self-service que o inclui).
- INCLUIDO: vem junto com outro módulo, sem preço próprio.
- GRATUITO: aberto a qualquer empresa cadastrada.
- BETA: existe, mas só é liberado pelo operador (não contratável).
- SOB_CONSULTA: existe e pode ser liberado pelo comercial; preço em definição.
- EM_DEFINICAO: preço e condições pendentes do Product Owner (§71).

Public Procurement é sempre EM_DEFINICAO com preço PENDING_DEFINITION até
a Fase 15, mesmo que algum plano o inclua por engano: a estrutura
`precificacao_pendente` lista os campos que o PO vai fornecer, todos
vazios. Nenhum valor é estimado.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

from sqlalchemy.orm import Session

from app.contexts.finops import contract as finops
from app.contexts.integrations import contract as integracoes
from app.models.cadencia import Cadencia
from app.models.campanha import Campanha
from app.models.conta_franquia_consumo import ContaFranquiaConsumo
from app.models.licenca import Licenca
from app.models.plano import Plano
from app.providers.plan_limits.base import PlanLimitsProvider
from app.services import auth_service


class Disponibilidade(StrEnum):
    DISPONIVEL = "DISPONIVEL"
    INCLUIDO = "INCLUIDO"
    GRATUITO = "GRATUITO"
    BETA = "BETA"
    SOB_CONSULTA = "SOB_CONSULTA"
    EM_DEFINICAO = "EM_DEFINICAO"


class StatusPreco(StrEnum):
    DEFINIDO = "DEFINIDO"  # preço nos planos (tabela `plano`)
    A_PARTIR_DE = "A_PARTIR_DE"  # Phase I: plano STARTING_AT, venda assistida
    INCLUIDO = "INCLUIDO"
    GRATUITO = "GRATUITO"
    PENDING_DEFINITION = "PENDING_DEFINITION"


# Campos que o PO fornecerá na Fase 15 (§ Fase 15). Ficam vazios até lá.
CAMPOS_PRECIFICACAO_PENDENTE = (
    "modelo_de_preco", "preco_mensal", "preco_anual", "usuarios_incluidos", "creditos_ia",
    "limites_api", "limites_procurement", "addons", "regras_de_excedente",
)


@dataclass(frozen=True)
class Produto:
    id: str
    nome: str
    descricao: str
    modulo: str | None = None  # chave de entitlement (`MODULOS`), quando houver
    incluido_com: str | None = None  # produto que o traz junto
    gratuito: bool = False
    venda_assistida: bool = False  # existe e o comercial pode liberar, sem preço público
    preco_pendente: bool = False
    recursos: tuple[str, ...] = field(default_factory=tuple)


PRODUTOS: tuple[Produto, ...] = (
    Produto("crm", "CRM", "Funil de vendas em Kanban, negócios, atividades, propostas e dashboard do time comercial.", modulo="crm",
            recursos=("Pipeline e estágios", "Atividades e agenda", "Propostas", "Dashboard de performance")),
    Produto("map", "MAP", "Saúde da carteira: score de risco, alertas de churn, economia da carteira e roteiro de resgate por IA.", modulo="map",
            recursos=("Score de risco e churn", "LTV, CAC e ROI", "Roteiro de resgate por IA", "MAP API")),
    Produto("predator", "PREDATOR", "Prospecção com IA: listas de contas, cadências e reunião qualificada, com aprovação humana antes de qualquer envio.",
            modulo="predator", recursos=("Geração de listas por ICP", "Cadências multicanal", "Aprovação humana", "Franquia de contas")),
    Produto("business_network", "Business Network (Shoal)", "Rede B2B: perfil, diretório, conexões, sinais de intenção e salas corporativas.",
            gratuito=True, recursos=("Perfil e diretório", "Conexões", "Sinais e intenções", "Salas corporativas")),
    Produto("opportunity_intelligence", "Opportunity Intelligence", "Necessidades, próxima melhor oferta, próxima ação e white space, sempre com evidência.",
            incluido_com="crm", recursos=("Necessidades com evidência", "Next best offer / action", "White space")),
    # Phase I (D-059): Public e Enterprise Bids no mesmo produto, sem cobrança por a oportunidade ser pública ou privada
    Produto("bid_intelligence", "Bid Intelligence",
            "Oportunidades públicas e privadas do lado vendedor: edital, TR e RFP com evidência, conformidade, Go/No-Go e proposta.",
            modulo="bids",
            recursos=("Licitações e RFI/RFP/RFQ privados", "Análise de edital e TR", "Matriz de conformidade",
                      "Go/No-Go com decisão humana", "Esboço de proposta", "Cofre de documentos")),
    Produto("public_procurement", "Public Procurement", "Compras públicas do lado comprador: PCA, demandas, processos, contratos e fornecedores.",
            modulo="procurement", preco_pendente=True,
            recursos=("Plano de contratações", "Processos e auditoria", "Supplier 360", "Sinais de risco para revisão")),
    Produto("strategic_sourcing", "Strategic Sourcing",
            "Compras privadas do lado comprador: RFI, RFP e RFQ, descoberta de fornecedores, portal do fornecedor, comparação e contrato.",
            modulo="sourcing",
            recursos=("RFI, RFP, RFQ e qualificação", "Descoberta na Business Network", "Portal do fornecedor sem assento",
                      "Comparação e aprovação humana", "IA de requisitos e avaliação com evidência")),
    Produto("strategic_sourcing_enterprise", "Strategic Sourcing Enterprise",
            "Strategic Sourcing com condições por contrato e pool de AI Credits do contrato.",
            modulo="sourcing_enterprise", venda_assistida=True,
            recursos=("Tudo do Strategic Sourcing", "Pool de AI Credits por contrato", "Condições comerciais por contrato")),
    Produto("api_access", "API Access", "API de produto com chaves por escopo e webhooks de saída, para os módulos contratados.",
            incluido_com="plano", recursos=("Chaves com escopo", "Webhooks assinados", "Idempotência")),
)


def _planos_self_service(db: Session) -> list[Plano]:
    return db.query(Plano).filter_by(visivel_self_service=True).order_by(Plano.categoria, Plano.preco_mensal).all()


def _planos_a_partir_de(db: Session) -> list[Plano]:
    """Phase I: planos "a partir de" (venda assistida). Aparecem no catálogo, nunca no checkout."""
    return db.query(Plano).filter_by(tipo_preco="STARTING_AT").order_by(Plano.preco_mensal).all()


def _estado(produto: Produto, planos: list[Plano], a_partir_de: list[Plano] = ()) -> tuple[Disponibilidade, StatusPreco, list[str]]:
    def contendo(lista: list[Plano]) -> list[str]:
        return [p.nome for p in lista if produto.modulo and produto.modulo in (p.modulos_contratados or [])]

    incluso_em = contendo([p for p in planos if p.tipo_preco == "FIXED"])
    if produto.preco_pendente and not produto.venda_assistida:
        return Disponibilidade.EM_DEFINICAO, StatusPreco.PENDING_DEFINITION, []
    if produto.gratuito:
        return Disponibilidade.GRATUITO, StatusPreco.GRATUITO, []
    if produto.incluido_com:
        return Disponibilidade.INCLUIDO, StatusPreco.INCLUIDO, []
    if incluso_em and not produto.preco_pendente:
        return Disponibilidade.DISPONIVEL, StatusPreco.DEFINIDO, incluso_em
    if contendo(list(a_partir_de)) and not produto.preco_pendente:  # Phase I: "a partir de", venda assistida
        return Disponibilidade.SOB_CONSULTA, StatusPreco.A_PARTIR_DE, contendo(list(a_partir_de))
    if produto.venda_assistida:
        return Disponibilidade.SOB_CONSULTA, StatusPreco.PENDING_DEFINITION, []
    return Disponibilidade.EM_DEFINICAO, StatusPreco.PENDING_DEFINITION, []


def _conectores() -> dict:
    registry = integracoes.obter_registry()
    itens = []
    for conector in registry.listar_conectores():
        if conector.status.value == "AVAILABLE":
            estado = Disponibilidade.INCLUIDO
        elif conector.status.value == "BETA":
            estado = Disponibilidade.BETA
        else:
            estado = Disponibilidade.EM_DEFINICAO
        itens.append({"sistema": conector.sistema, "nome": conector.nome, "disponibilidade": estado,
                      "liberado_para_conexao": registry.conectavel(conector.sistema)})
    return {
        "id": "connectors", "nome": "Conectores de CRM",
        "descricao": "Leitura de CRMs externos pelo modelo canônico (MAP sobre o seu CRM). Conectores em beta são liberados pelo operador.",
        "disponibilidade": Disponibilidade.BETA if any(i["disponibilidade"] == Disponibilidade.BETA for i in itens) else Disponibilidade.INCLUIDO,
        "status_preco": StatusPreco.INCLUIDO, "conectores": itens,
    }


def _creditos_ia(db: Session) -> dict:
    """Fase 15: AI Credits à venda. Preços vêm do catálogo versionado de
    pacotes do FinOps (fonte única); aqui só se referencia."""
    pacotes = [finops.catalogos.pacote_dict(p) for p in finops.catalogos.pacotes_vigentes(db)]
    return {
        "id": "ai_credits", "nome": "B2B ON AI Credits",
        "descricao": "Cada plano inclui AI Credits mensais; pacotes adicionais valem por 12 meses. "
                     "Uma carteira compartilhada por empresa, consumida pelo que vence primeiro.",
        "disponibilidade": Disponibilidade.DISPONIVEL, "status_preco": StatusPreco.DEFINIDO,
        "pacotes": pacotes, "franquias": finops.comercial.franquias_publicas(),
    }


def _plano_publico(plano: Plano) -> dict:
    return {
        "id": plano.id, "nome": plano.nome, "categoria": plano.categoria, "preco_mensal": plano.preco_mensal,
        "tipo_preco": plano.tipo_preco, "self_service": plano.visivel_self_service and plano.tipo_preco == "FIXED",
        "usuarios_incluidos": plano.max_usuarios,  # Phase J3: included_users do plano; adicionais ficam na licença
        "ai_credits_mensais": finops.comercial.franquia_mensal(list(plano.modulos_contratados or []))[0],
        "max_usuarios": plano.max_usuarios, "modulos": list(plano.modulos_contratados or []),
        "limites": {
            "franquia_contas_mes": plano.franquia_contas_mes, "cadencias_mes": plano.limite_cadencias_mes,
            "campanhas_mes": plano.limite_campanhas_mes, "enriquecimento_site_semanal": plano.limite_enriquecimento_site_semanal,
            "enriquecimento_contatos_semanal": plano.limite_enriquecimento_contatos_semanal,
        },
        "recursos": {
            "ab_teste_cadencia": plano.permite_ab_teste_cadencia, "auto_aprovacao": plano.permite_auto_aprovacao,
            "webhook_relatorio": plano.permite_webhook_relatorio, "api_parceiros": plano.permite_api_parceiros,
            "subtenants": plano.permite_subtenants, "registro_oportunidade": plano.permite_registro_oportunidade,
        },
    }


# --- Linhas comerciais (Phase I, D-059): o que a página de vendas oferece --------------------------
@dataclass(frozen=True)
class LinhaComercial:
    id: str
    nome: str
    descricao: str
    lado: str  # SELL | BUY
    produtos: tuple[str, ...]  # ids de PRODUTOS
    modulos: tuple[str, ...]  # um plano entra na linha se contém algum destes e nenhum de fora dela
    pendencias: tuple[str, ...] = ()  # o que o PO ainda não definiu: aparece "a definir", nunca um número


LINHAS: tuple[LinhaComercial, ...] = (
    LinhaComercial("revenue_intelligence", "B2B ON Revenue Intelligence",
                   "Prospectar, vender e expandir: CRM, MAP, PREDATOR e Opportunity Intelligence.", "SELL",
                   ("crm", "map", "predator", "opportunity_intelligence"), ("crm", "map", "predator")),
    LinhaComercial("bid_intelligence", "B2B ON Bid Intelligence",
                   "Encontrar, qualificar, analisar e responder oportunidades públicas e privadas.", "SELL",
                   ("bid_intelligence",), ("bids",), pendencias=("preco_usuario_adicional",)),  # J3: 10 incluídos (OI-023)
    LinhaComercial("public_procurement", "B2B ON Public Procurement",
                   "Planejar e executar contratações públicas.", "BUY", ("public_procurement",), ("procurement",),
                   pendencias=("preco", "creditos_ia")),
    LinhaComercial("strategic_sourcing", "B2B ON Strategic Sourcing",
                   "Encontrar, qualificar, comparar e contratar fornecedores.", "BUY",
                   ("strategic_sourcing", "strategic_sourcing_enterprise"), ("sourcing", "sourcing_enterprise")),
    LinhaComercial("suite", "B2B ON Suite", "Todos os produtos B2B ON numa assinatura.", "SELL",
                   (), (), pendencias=("preco", "creditos_ia")),
)


def _linhas(planos: list[Plano], a_partir_de: list[Plano]) -> list[dict]:
    resultado = []
    for linha in LINHAS:
        dela = [p for p in [*planos, *a_partir_de] if linha.modulos and set(p.modulos_contratados or []) & set(linha.modulos)
                and set(p.modulos_contratados or []) <= set(linha.modulos) and p.preco_mensal > 0]
        if "preco" in linha.pendencias:
            dela = []  # preço em definição: nenhum plano é oferecido, mesmo que exista por engano
        resultado.append({
            "id": linha.id, "nome": linha.nome, "descricao": linha.descricao, "lado": linha.lado, "produtos": list(linha.produtos),
            "planos": [_plano_publico(p) for p in dela], "pendencias": list(linha.pendencias),
            "status_preco": StatusPreco.PENDING_DEFINITION if "preco" in linha.pendencias or not dela else StatusPreco.DEFINIDO,
        })
    return resultado


def catalogo(db: Session) -> dict:
    planos = _planos_self_service(db)
    a_partir_de = _planos_a_partir_de(db)
    produtos = []
    for produto in PRODUTOS:
        disponibilidade, status_preco, incluso_em = _estado(produto, planos, a_partir_de)
        item = {
            "id": produto.id, "nome": produto.nome, "descricao": produto.descricao, "modulo": produto.modulo,
            "incluido_com": produto.incluido_com, "recursos": list(produto.recursos), "disponibilidade": disponibilidade,
            "status_preco": status_preco, "planos": incluso_em,
        }
        if status_preco == StatusPreco.PENDING_DEFINITION:
            item["precificacao_pendente"] = dict.fromkeys(CAMPOS_PRECIFICACAO_PENDENTE)
        produtos.append(item)
    produtos.append(_conectores())
    produtos.append(_creditos_ia(db))
    return {"moeda": "BRL", "produtos": produtos, "planos": [_plano_publico(p) for p in planos],
            "linhas": _linhas(planos, a_partir_de)}


# --- Assinatura do tenant -------------------------------------------------------------


def _inicio_do_mes() -> datetime:
    return datetime.now(UTC).replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _uso(usado: int, limite: int | None) -> dict:
    return {"usado": usado, "limite": limite, "percentual": round(usado / limite * 100) if limite else None}


def assinatura(db: Session, tenant_id: str, plan_limits: PlanLimitsProvider) -> dict:
    """Plano, módulos e uso do tenant. Tudo filtrado pelo tenant; custo em
    dólar da IA não é exposto (só chamadas e créditos)."""
    licenca = db.query(Licenca).filter_by(tenant_id=tenant_id).one_or_none()
    plano = db.get(Plano, licenca.plano_id) if licenca else None
    inicio = _inicio_do_mes()
    catalogo_atual = catalogo(db)
    modulos = [
        {"id": p["id"], "nome": p["nome"], "modulo": p["modulo"], "disponibilidade": p["disponibilidade"],
         "contratado": plan_limits.permite_modulo(tenant_id, p["modulo"])}
        for p in catalogo_atual["produtos"] if p.get("modulo")
    ]
    usuarios = auth_service.contar_assentos(db, tenant_id)  # Phase J3: só assentos internos
    franquia = db.query(ContaFranquiaConsumo).filter_by(tenant_id=tenant_id, ano_mes=inicio.strftime("%Y-%m")).count()
    cadencias = db.query(Cadencia).filter(Cadencia.tenant_id == tenant_id, Cadencia.criado_em >= inicio).count()
    campanhas = db.query(Campanha).filter(Campanha.tenant_id == tenant_id, Campanha.criado_em >= inicio).count()
    ia = finops.dashboard.resumo(db, inicio, datetime.now(UTC), tenant_id=tenant_id)
    return {
        "plano": {"nome": plano.nome, "categoria": plano.categoria, "preco_mensal": plano.preco_mensal, "tipo_preco": plano.tipo_preco,
                  "ai_credits_mensais": finops.comercial.franquia_mensal(list(plano.modulos_contratados or []))[0]} if plano else None,
        "licenca": {"status": licenca.status, "expira_em": licenca.data_expiracao.isoformat() if licenca and licenca.data_expiracao else None}
        if licenca else {"status": "sem_licenca", "expira_em": None},
        "modulos": modulos,
        "uso": {
            "periodo": inicio.strftime("%Y-%m"),
            "usuarios": _uso(usuarios, auth_service.limite_de_usuarios(db, tenant_id)),  # plano + adicionais
            "franquia_contas": _uso(franquia, plan_limits.obter_franquia_contas_mes(tenant_id)),
            "cadencias": _uso(cadencias, plan_limits.obter_limite_cadencias_mes(tenant_id)),
            "campanhas": _uso(campanhas, plan_limits.obter_limite_campanhas_mes(tenant_id)),
        },
        "ia": {
            "chamadas_no_mes": ia["totais"]["chamadas"], "creditos_consumidos": ia["totais"]["creditos_consumidos"],
            "saldo_creditos": float(finops.carteira.disponivel(db, tenant_id)),
            "franquia_mensal": finops.carteira.franquia_do_tenant(db, tenant_id)[0],
        },
        "conectores": next(p for p in catalogo_atual["produtos"] if p["id"] == "connectors")["conectores"],
    }
