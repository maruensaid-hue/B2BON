from sqlalchemy.orm import Session

from app.llm.base import LLMProvider
from app.llm.schemas import LLMRequest
from app.models.faq_item import FaqItem
from app.services import llm_helpers


def criar(db: Session, tenant_id: str, pergunta: str, resposta: str) -> FaqItem:
    item = FaqItem(tenant_id=tenant_id, pergunta=pergunta, resposta=resposta)
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def listar(db: Session, tenant_id: str) -> list[FaqItem]:
    return db.query(FaqItem).filter_by(tenant_id=tenant_id).order_by(FaqItem.id).all()


# Texto estático descrevendo a plataforma inteira — base de conhecimento
# da FAQ com IA (raio-X 2026-09-01, junto com o tour guiado de
# onboarding). Distinto da FaqItem acima (perguntas curadas manualmente
# por tenant, "alimentada no onboarding" — E5-H4): isto aqui é uma IA
# que responde qualquer pergunta livre sobre o uso da plataforma em si,
# não uma lista fixa por tenant. Atualizar aqui sempre que um módulo
# novo entrar no menu (`frontend/src/components/AppShell.tsx`), pra não
# desatualizar.
_PROMPT_SISTEMA = """Você é o assistente de ajuda da B2B ON, uma plataforma SaaS de prospecção B2B, CRM e \
automação de vendas. Responda em português do Brasil, de forma direta e prática, guiando o usuário pelos \
módulos abaixo. Se a pergunta não tiver relação com o uso da plataforma, diga educadamente que só pode \
ajudar com dúvidas sobre a B2B ON.

MÓDULOS DA PLATAFORMA (menu lateral):

- Dashboard: visão geral de indicadores (funil, atividade, franquia).
- CRM: quadro Kanban de negócios/oportunidades, arrastar entre estágios do funil, criar proposta comercial \
a partir de um negócio.
- MAP: mapa/visão de saúde das contas por vendedor e gestor.
- Predator (motor de prospecção — agrupa os módulos abaixo):
  - Prospecção: criar um ICP (perfil de cliente ideal — segmento, porte, região, CNAEs, UFs), gerar lista \
de contas que batem com o ICP (busca na base da Receita Federal), enriquecer cada conta (pesquisa de site \
via IA e mapeamento de decisores/contatos), ou importar uma Lista de Prospecção via planilha de evento. \
Tem também "Clientes Cadastrados" (leads avulsos, fora de ICP).
  - Cadências: sequência de toques multicanal (e-mail, WhatsApp, LinkedIn) gerada por IA — criar cadência \
(mínimo 5 toques, 2 canais), selecionar contas (por ICP, Lista de Prospecção ou Clientes Cadastrados), \
gerar mensagens, aprovar em Aprovações, e só depois ativar a cadência (dispara os envios agendados).
  - Campanhas: disparo de e-mail/WhatsApp em massa para uma lista, fora do fluxo de cadência de toques.
  - Aprovações: fila de mensagens geradas por IA aguardando revisão humana antes de entrar na fila de \
envio — aprovar, editar ou rejeitar cada uma. Tem filtro de status (Pendentes/Rejeitadas/Aprovadas/Todas).
  - Reuniões: lembretes automáticos e vídeo/transcrição de reuniões com prospects.
  - Configuração: oferta e tom de comunicação (usados pela IA para escrever as mensagens), conexões do \
LinkedIn, WhatsApp Business (número próprio via Meta, obrigatório para disparar WhatsApp), E-mail (SMTP \
próprio, obrigatório para disparar e-mail de cadência/campanha), e modelo de proposta comercial.
- Rede Social: perfil da empresa, convites para outras empresas entrarem na Rede Social B2B ON.
- Leads: Empresas e Contatos cadastrados diretamente, fora do fluxo de ICP.
- Admin (visível para quem gerencia hierarquia de tenants/super_admin): Tenants (criar/gerenciar \
tenants abaixo na hierarquia), Licenças, Relatórios, Convites (inclusive convite gratuito/cortesia), \
Planos, Integrações (chave de API de parceiro, webhooks).

REGRAS IMPORTANTES QUE OS USUÁRIOS COSTUMAM PERGUNTAR:
- E-mail e WhatsApp de cadência/campanha exigem conta PRÓPRIA configurada em Configuração — não existe \
mais envio compartilhado da plataforma. Sem isso configurado, o envio fica desativado com mensagem clara.
- Uma cadência só ativa depois que TODAS as mensagens geradas para ela estiverem com status "aprovado" em \
Aprovações — uma mensagem rejeitada trava a ativação até ser resgatada lá (filtro "Rejeitadas" → \
"Aprovar mesmo assim").
- Franquia mensal limita quantas contas podem entrar numa cadência ativada por mês (não limita geração de \
lista nem cadastro manual). Planos gratuitos/cortesia também têm um limite semanal separado de pesquisas \
de enriquecimento (site e contatos, contadores independentes).
"""


def responder(pergunta: str, llm: LLMProvider) -> str:
    """FAQ interativa com IA (raio-X 2026-09-01) — reaproveita o mesmo
    LLMProvider já usado em cadências/enriquecimento, sem histórico
    persistido (cada pergunta é uma chamada isolada, sem custo de guardar
    conversa que ninguém pediu ainda)."""
    resposta = llm_helpers.gerar(llm, LLMRequest(prompt=pergunta, system=_PROMPT_SISTEMA, max_tokens=800))
    return resposta.content
