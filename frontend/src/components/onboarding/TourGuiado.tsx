import { GuiaPassoAPasso, type PassoGuia } from "@/components/onboarding/GuiaPassoAPasso";

// Um passo por módulo do menu lateral (raio-X 2026-09-01), com uma
// "visita detalhada" a mais passos dentro de PREDATOR e SHOAL (pedido
// 2026-09-20) — ainda sem clique-a-clique em cada ação de cada tela
// (dúvidas mais específicas continuam na FAQ com IA), só um passo por
// SUB-MÓDULO real em vez de um parágrafo único cobrindo os nove de
// uma vez. Cada `id` casa com um `data-tour-id` marcado em
// AppShell.tsx (`nav:${path}` nos itens de menu, ou um id fixo nos
// contêineres de seção); passos cujo elemento não existe no DOM no
// momento (ex.: "admin" pra quem não gerencia hierarquia, ou os
// sub-passos de Predator pra quem não tem licença ativa) são pulados
// automaticamente (mecânica em `GuiaPassoAPasso.tsx`, raio-X
// 2026-09-21 — extraída daqui pra ser reaproveitada pelos tutoriais
// por módulo). `grupoToggle` é só usado pelos sub-passos de Predator:
// o grupo do menu nasce recolhido, então o guia clica no
// `data-tour-toggle` correspondente (ver AppShell.tsx) pra abri-lo
// sozinho antes de destacar o item de dentro.
const PASSOS_TOUR: PassoGuia[] = [
  {
    id: "dashboard",
    titulo: "Dashboard",
    descricao: "Visão geral com os principais indicadores: funil de vendas, atividade recente e franquia do mês.",
  },
  {
    id: "crm",
    titulo: "CRM",
    descricao:
      "Seu quadro Kanban de negócios — arraste oportunidades entre os estágios do funil, gere propostas comerciais a partir de um negócio, e use \"Editar Funil\" (Admin/Super Admin) pra criar ou renomear filas próprias.",
  },
  {
    id: "map",
    titulo: "MAP",
    descricao: "Mapa de saúde das suas contas — acompanhe o que cada vendedor está trabalhando.",
  },
  {
    id: "predator",
    titulo: "Predator — motor de prospecção",
    descricao:
      "O motor pago de prospecção B2B da plataforma, com nove módulos — os próximos passos visitam cada um.",
  },
  {
    id: "nav:/prospeccao",
    titulo: "Predator — Prospecção",
    descricao:
      "Crie um ICP (segmento, porte, região, CNAEs), gere uma lista de contas que batem com ele direto na base da Receita Federal, enriqueça cada conta (site + decisores via IA), ou importe uma Lista de Prospecção via planilha.",
    grupoToggle: "predator",
  },
  {
    id: "nav:/cadencias",
    titulo: "Predator — Cadências",
    descricao:
      "Sequências de toques multicanal (e-mail, WhatsApp, LinkedIn) escritas por IA — crie, gere as mensagens, aprove em Aprovações e só depois ative pra disparar.",
    grupoToggle: "predator",
  },
  {
    id: "nav:/campanhas",
    titulo: "Predator — Campanhas",
    descricao: "Disparo de e-mail/WhatsApp em massa pra uma lista, fora do fluxo de cadência de toques.",
    grupoToggle: "predator",
  },
  {
    id: "nav:/aprovacoes",
    titulo: "Predator — Aprovações",
    descricao:
      "Toda mensagem que a IA escreve passa por aqui antes de ser enviada — aprove, edite ou rejeite, com filtro por status.",
    grupoToggle: "predator",
  },
  {
    id: "nav:/reunioes",
    titulo: "Predator — Reuniões",
    descricao: "Lembretes automáticos e vídeo/transcrição das reuniões marcadas com seus prospects.",
    grupoToggle: "predator",
  },
  {
    id: "nav:/relatorio-entrega",
    titulo: "Predator — Relatório de Entrega",
    descricao:
      "Taxa de abertura/clique/resposta de e-mail e WhatsApp, com bloqueio automático de contatos com muito bounce.",
    grupoToggle: "predator",
  },
  {
    id: "nav:/regras-aprendidas",
    titulo: "Predator — Regras Aprendidas",
    descricao:
      "Cadastre regras de estilo/conteúdo que entram sozinhas no prompt da próxima cadência — a IA pode sugerir o texto a partir de uma correção recente sua.",
    grupoToggle: "predator",
  },
  {
    id: "nav:/inteligencia-rede",
    titulo: "Predator — Sinais de Oportunidade",
    descricao: "Fit de ICP contra a rede Shoal, matches de necessidades declaradas e riscos de pipeline — sempre com o motivo explicado.",
    grupoToggle: "predator",
  },
  {
    id: "nav:/agente-corporativo",
    titulo: "Predator — Agente Corporativo",
    descricao:
      "Um assistente de IA que responde, sob revisão humana, perguntas que outras empresas do Shoal fazem sobre a sua.",
    grupoToggle: "predator",
  },
  {
    id: "nav:/configuracao",
    titulo: "Predator — Configuração",
    descricao:
      "Oferta e tom de comunicação usados pela IA, conexões de WhatsApp/E-mail/LinkedIn (obrigatórias pra disparar), e modelo de proposta.",
    grupoToggle: "predator",
  },
  {
    id: "nav:/rede-social",
    titulo: "Shoal — a rede social B2B",
    descricao:
      "Camada gratuita da plataforma — funciona mesmo sem licença ativa do Predator. Os próximos passos visitam cada área.",
  },
  {
    id: "nav:/rede-social",
    titulo: "Shoal — Perfil e Verificação",
    descricao:
      "Logo, capa, setor, porte, mercados, produtos/serviços e certificações da sua empresa. Solicite verificação com um e-mail corporativo pra ganhar o selo.",
  },
  {
    id: "nav:/rede-social",
    titulo: "Shoal — Diretório e Conexões",
    descricao:
      "Busque empresas por setor/porte/mercado, conecte-se (com aceite mútuo) ou siga sem aceite; bloqueie ou desconecte quando precisar.",
  },
  {
    id: "nav:/rede-social",
    titulo: "Shoal — Mensagens e Salas Corporativas",
    descricao:
      "Converse por DM com uma empresa conectada, ou abra uma Sala Corporativa com canais (Geral, Comercial, Técnico...) pra assuntos mais estruturados.",
  },
  {
    id: "nav:/rede-social",
    titulo: "Shoal — Feed da Rede",
    descricao:
      "Publique posts com legenda, carrossel de fotos ou vídeo; comente, reaja (9 emojis) e compartilhe o que outras empresas publicam.",
  },
  {
    id: "nav:/rede-social",
    titulo: "Shoal — Necessidades da Rede",
    descricao:
      "Publique o que sua empresa está procurando (categoria, requisitos, orçamento) pra rede toda ou só suas conexões verem.",
  },
  {
    id: "nav:/rede-social",
    titulo: "Shoal — Convidar Empresa",
    descricao:
      "Gere um link pra uma empresa nova entrar no Shoal — qualquer pessoa da sua empresa pode gerar (o convite gratuito/cortesia é restrito a Admin/Super Admin).",
  },
  {
    id: "leads",
    titulo: "Leads",
    descricao: "Empresas e Contatos cadastrados diretamente, fora do fluxo de ICP.",
  },
  {
    id: "admin",
    titulo: "Admin",
    descricao:
      "Gestão de tenants/licenças/relatórios (hierarquia), Convites (traz um colega pro seu próprio tenant — qualquer Admin já pode gerar) e Planos/Verificações (Super Admin) — visível conforme o seu papel.",
  },
];

interface TourGuiadoProps {
  open: boolean;
  onClose: () => void;
}

export function TourGuiado({ open, onClose }: TourGuiadoProps) {
  return (
    <GuiaPassoAPasso
      open={open}
      onClose={onClose}
      passos={PASSOS_TOUR}
      atributoSeletor="data-tour-id"
      atributoToggle="data-tour-toggle"
    />
  );
}
