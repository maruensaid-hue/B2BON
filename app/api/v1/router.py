from fastapi import APIRouter, Depends

from app.api.deps import exigir_algum_modulo, exigir_licenca_ativa, exigir_modulo
from app.api.v1.admin_tenants import router as admin_tenants_router
from app.api.v1.agente_corporativo import router as agente_corporativo_router
from app.api.v1.aprovacoes import router as aprovacoes_router
from app.api.v1.auditoria import router as auditoria_router
from app.api.v1.auth import router as auth_router
from app.api.v1.bids import router as bids_router
from app.api.v1.busca import router as busca_router
from app.api.v1.cadencias import router as cadencias_router
from app.api.v1.campanhas import router as campanhas_router
from app.api.v1.canais import router as canais_router
from app.api.v1.captura_lead import router as captura_lead_router
from app.api.v1.central_negocios import router as central_negocios_router
from app.api.v1.comunicacao import router as comunicacao_router
from app.api.v1.configuracao_envio import router as configuracao_envio_router
from app.api.v1.configuracao_email_smtp import router as configuracao_email_smtp_router
from app.api.v1.configuracao_whatsapp import router as configuracao_whatsapp_router
from app.api.v1.contas import router as contas_router
from app.api.v1.listas_prospeccao import router as listas_prospeccao_router
from app.api.v1.convites import router as convites_router
from app.api.v1.crm import router as crm_router
from app.api.v1.conversas import router as conversas_router
from app.api.v1.ai_credits import router as ai_credits_router
from app.api.v1.cron import router as cron_router
from app.api.v1.decisores import router as decisores_router
from app.api.v1.email_direto import router as email_direto_router
from app.api.v1.envios import router as envios_router
from app.api.v1.faq import router as faq_router
from app.api.v1.finops import router as finops_router
from app.api.v1.icp import router as icp_router
from app.api.v1.indicacoes import router as indicacoes_router
from app.api.v1.inteligencia_rede import router as inteligencia_rede_router
from app.api.v1.inteligencia_rede import router_crm as inteligencia_rede_crm_router
from app.api.v1.integracoes import router as integracoes_router
from app.api.v1.inteligencia import router as inteligencia_router
from app.api.v1.leads import router as leads_router
from app.api.v1.linkedin import router as linkedin_router
from app.api.v1.motor import router as motor_router
from app.api.v1.notificacoes import router as notificacoes_router
from app.api.v1.nps import router as nps_router
from app.api.v1.ofertas import router as oferta_router
from app.api.v1.oportunidades import router as oportunidades_router
from app.api.v1.revenue_intelligence import router as revenue_intelligence_router
from app.api.v1.onboarding import router as onboarding_router
from app.api.v1.optout import router as optout_router
from app.api.v1.painel import router as painel_router
from app.api.v1.parceiros import router as parceiros_router
from app.api.v1.catalogo import router as catalogo_router
from app.api.v1.planos import router as planos_router
from app.api.v1.plataforma_api import router as plataforma_api_router
from app.api.v1.produto.map_api import router as map_api_router
from app.api.v1.produto.predator_api import router as predator_api_router
from app.api.v1.procurement import router as procurement_router
from app.api.v1.portal_fornecedor import router_link as portal_fornecedor_link_router
from app.api.v1.portal_fornecedor import router_rede as portal_fornecedor_rede_router
from app.api.v1.strategic_sourcing import router as strategic_sourcing_router
from app.api.v1.prospeccao_contas import router as prospeccao_contas_router
from app.api.v1.regras_aprendidas import router as regras_aprendidas_router
from app.api.v1.relatorios import router as relatorios_router
from app.api.v1.representantes import router as representantes_router
from app.api.v1.rotulos_hierarquia import router as rotulos_hierarquia_router
from app.api.v1.qualificacao import router as qualificacao_router
from app.api.v1.rede_social import router as rede_social_router
from app.api.v1.registro_oportunidade import router as registro_oportunidade_router
from app.api.v1.relatorio_entrega import router as relatorio_entrega_router
from app.api.v1.reunioes import router as reunioes_router
from app.api.v1.ropa import router as ropa_router
from app.api.v1.saude_conta import router as saude_conta_router
from app.api.v1.template_proposta import router as template_proposta_router
from app.api.v1.titulares import router as titulares_router
from app.api.v1.usuarios import router as usuarios_router
from app.api.v1.verificacao_empresa import router as verificacao_empresa_router
from app.api.v1.webhooks import router as webhooks_router
from app.api.v1.whatsapp import router as whatsapp_router

router = APIRouter()

# Módulos pagos (PREDATOR/CRM/MAP) — travados para tenants sem licença
# ativa (Onda H: convite-vitrine só dá acesso à Rede Social). Auth,
# convites, planos, admin de tenant, webhooks/optout/cron (públicos,
# com seu próprio mecanismo de autenticação) e a própria Rede Social
# ficam de fora deliberadamente.
#
# Contratação avulsa por módulo (raio-X 2026-09-24): além de licença
# ativa, cada router de MAP/PREDATOR/CRM agora também exige que o plano
# da licença tenha aquele módulo específico em `modulos_contratados`
# (`exigir_modulo`) — um plano de suíte libera os três, um plano avulso
# só o seu. Routers "compartilhados" (ajuda, onboarding, notificações,
# gestão de usuários do próprio tenant, etc.) continuam só com
# `_exige_licenca`, sem amarrar a nenhum módulo específico.
_exige_licenca = [Depends(exigir_licenca_ativa)]
_exige_map = [Depends(exigir_licenca_ativa), Depends(exigir_modulo("map"))]
_exige_predator = [Depends(exigir_licenca_ativa), Depends(exigir_modulo("predator"))]
_exige_crm = [Depends(exigir_licenca_ativa), Depends(exigir_modulo("crm"))]
_exige_bids = [Depends(exigir_licenca_ativa), Depends(exigir_modulo("bids"))]
_exige_procurement = [Depends(exigir_licenca_ativa), Depends(exigir_modulo("procurement"))]
_exige_sourcing = [Depends(exigir_licenca_ativa), Depends(exigir_modulo("sourcing"))]
# Fase 1 (D-007): rotas legitimamente compartilhadas entre módulos.
# Organization/Person (Conta/Decisor/lead) é Shared Kernel — CRM e
# PREDATOR precisam das duas (o Kanban do CRM cria conta por
# `/leads/contas`, acoplamento C4). Oferta é referenciada por
# `Negocio.oferta_id` (C5). NPS alimenta o CS Score do MAP (C6).
_exige_organizacao = [Depends(exigir_licenca_ativa), Depends(exigir_algum_modulo("crm", "predator"))]
_exige_oferta = [Depends(exigir_licenca_ativa), Depends(exigir_algum_modulo("crm", "predator"))]
_exige_nps = [Depends(exigir_licenca_ativa), Depends(exigir_algum_modulo("map", "predator"))]

router.include_router(icp_router, dependencies=_exige_predator)
router.include_router(oferta_router, dependencies=_exige_oferta)
router.include_router(comunicacao_router, dependencies=_exige_licenca)
router.include_router(onboarding_router, dependencies=_exige_licenca)
# Prospecção (C3) ANTES de `contas`: `/contas/franquia` não pode cair em
# `/contas/{conta_id}`.
router.include_router(prospeccao_contas_router, dependencies=_exige_predator)
router.include_router(contas_router, dependencies=_exige_organizacao)
router.include_router(listas_prospeccao_router, dependencies=_exige_predator)
router.include_router(aprovacoes_router, dependencies=_exige_predator)
router.include_router(auditoria_router)
router.include_router(ropa_router, dependencies=_exige_predator)
router.include_router(cadencias_router, dependencies=_exige_predator)
router.include_router(regras_aprendidas_router, dependencies=_exige_predator)
router.include_router(email_direto_router, dependencies=_exige_predator)
router.include_router(busca_router, dependencies=_exige_predator)
router.include_router(campanhas_router, dependencies=_exige_predator)
router.include_router(envios_router, dependencies=_exige_predator)
router.include_router(whatsapp_router, dependencies=_exige_predator)
router.include_router(webhooks_router)
router.include_router(optout_router)
router.include_router(cron_router)
# AI Credits (Fase 15): pacotes/workloads públicos; carteira do tenant exige login.
router.include_router(ai_credits_router)
# Endpoint público sem licença (link de captura de lead por CTA de
# anúncio/site) + um endpoint autenticado (`/config`) só pra gerar/exibir
# o link do próprio tenant — mesmo raciocínio de `webhooks_router`/
# `optout_router` acima.
router.include_router(captura_lead_router)
router.include_router(configuracao_envio_router, dependencies=_exige_predator)
router.include_router(configuracao_whatsapp_router, dependencies=_exige_predator)
router.include_router(configuracao_email_smtp_router, dependencies=_exige_predator)
router.include_router(linkedin_router, dependencies=_exige_predator)
router.include_router(canais_router, dependencies=_exige_predator)
router.include_router(relatorio_entrega_router, dependencies=_exige_predator)
router.include_router(qualificacao_router, dependencies=_exige_predator)
router.include_router(conversas_router, dependencies=_exige_predator)
router.include_router(notificacoes_router, dependencies=_exige_licenca)
router.include_router(decisores_router, dependencies=_exige_organizacao)
router.include_router(reunioes_router, dependencies=_exige_predator)
router.include_router(titulares_router, dependencies=_exige_licenca)
router.include_router(faq_router, dependencies=_exige_licenca)
router.include_router(painel_router, dependencies=_exige_licenca)
router.include_router(nps_router, dependencies=_exige_nps)
router.include_router(indicacoes_router, dependencies=_exige_licenca)
router.include_router(leads_router, dependencies=_exige_organizacao)
router.include_router(auth_router)
router.include_router(convites_router)
router.include_router(planos_router)
router.include_router(catalogo_router)
router.include_router(representantes_router)
router.include_router(central_negocios_router)
router.include_router(rotulos_hierarquia_router)
router.include_router(admin_tenants_router)
# Fase 2 da hierarquia (raio-X): /integracoes é JWT (Distribuidor logado
# gerenciando chave/webhook próprios), /parceiros é chave de API (sistema
# do Distribuidor chamando de fora) — nenhum dos dois passa por
# exigir_licenca_ativa, mesmo raciocínio de /admin/tenants (administrativo,
# não módulo pago do PREDATOR).
router.include_router(integracoes_router)
router.include_router(parceiros_router)
router.include_router(relatorios_router)
router.include_router(crm_router, dependencies=_exige_crm)
router.include_router(oportunidades_router, dependencies=_exige_crm)
router.include_router(revenue_intelligence_router, dependencies=_exige_crm)
router.include_router(bids_router, dependencies=_exige_bids)
router.include_router(procurement_router, dependencies=_exige_procurement)
router.include_router(strategic_sourcing_router, dependencies=_exige_sourcing)
# Portal do fornecedor (Phase F): por link, sem login nem licença (Supplier Guest, com rate limit por IP);
# pela conta da rede, só login — o fornecedor não precisa contratar nada para responder.
router.include_router(portal_fornecedor_link_router)
router.include_router(portal_fornecedor_rede_router)
router.include_router(rede_social_router)
router.include_router(inteligencia_rede_router, dependencies=_exige_predator)
router.include_router(inteligencia_rede_crm_router, dependencies=_exige_organizacao)
router.include_router(agente_corporativo_router, dependencies=_exige_predator)
router.include_router(verificacao_empresa_router)
# /motor é ferramenta interna do super_admin/CyberFort (cross-tenant, já
# travada por papel no próprio APIRouter) — não é o "MAP" vendido ao
# cliente, por isso fica só em `_exige_licenca`, sem `exigir_modulo`.
router.include_router(motor_router, dependencies=_exige_licenca)
# MAP de contas — visível a user/admin/super_admin dentro do próprio
# tenant (escopo aplicado no serviço), distinto do /motor acima (só
# super_admin, cross-tenant). Este sim é o módulo MAP vendido avulso.
router.include_router(saude_conta_router, dependencies=_exige_map)
router.include_router(registro_oportunidade_router, dependencies=_exige_predator)
router.include_router(usuarios_router, dependencies=_exige_licenca)
router.include_router(template_proposta_router, dependencies=_exige_crm)
# Fase 3 — plataforma de API. Gestão (JWT, admin) exige licença ativa;
# a API de produto autentica por chave de API (`autenticar_api` faz
# licença + módulo + escopo por conta própria, sem JWT).
router.include_router(plataforma_api_router, dependencies=_exige_licenca)
router.include_router(map_api_router)
router.include_router(predator_api_router)
# Fase 4 — B2B ON Intelligence (Corporate Brain, perfis, aprendizado, auditoria de IA).
router.include_router(inteligencia_router, dependencies=_exige_licenca)
# Fase 5 — AI FinOps & Credits. Sem gate de licença: o super_admin opera a
# plataforma; as rotas do tenant exigem papel admin (checado no router).
router.include_router(finops_router)
