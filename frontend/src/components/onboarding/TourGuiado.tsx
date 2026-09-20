import { useEffect, useState } from "react";

// Um passo por módulo do menu lateral (raio-X 2026-09-01), com uma
// "visita detalhada" a mais passos dentro de PREDATOR e SHOAL (pedido
// 2026-09-20) — ainda sem clique-a-clique em cada ação de cada tela
// (dúvidas mais específicas continuam na FAQ com IA), só um passo por
// SUB-MÓDULO real em vez de um parágrafo único cobrindo os nove de
// uma vez. Cada `tourId` casa com um `data-tour-id` marcado em
// AppShell.tsx (`nav:${path}` nos itens de menu, ou um id fixo nos
// contêineres de seção); passos cujo elemento não existe no DOM no
// momento (ex.: "admin" pra quem não gerencia hierarquia, ou os
// sub-passos de Predator pra quem não tem licença ativa) são pulados
// automaticamente. `grupoToggle` é só usado pelos sub-passos de
// Predator: o grupo do menu nasce recolhido, então o tour clica no
// `data-tour-toggle` correspondente (ver AppShell.tsx) pra abri-lo
// sozinho antes de destacar o item de dentro.
interface PassoTour {
  tourId: string;
  titulo: string;
  descricao: string;
  grupoToggle?: string;
}

const PASSOS_TOUR: PassoTour[] = [
  {
    tourId: "dashboard",
    titulo: "Dashboard",
    descricao: "Visão geral com os principais indicadores: funil de vendas, atividade recente e franquia do mês.",
  },
  {
    tourId: "crm",
    titulo: "CRM",
    descricao:
      "Seu quadro Kanban de negócios — arraste oportunidades entre os estágios do funil, gere propostas comerciais a partir de um negócio, e use \"Editar Funil\" (Admin/Super Admin) pra criar ou renomear filas próprias.",
  },
  {
    tourId: "map",
    titulo: "MAP",
    descricao: "Mapa de saúde das suas contas — acompanhe o que cada vendedor está trabalhando.",
  },
  {
    tourId: "predator",
    titulo: "Predator — motor de prospecção",
    descricao:
      "O motor pago de prospecção B2B da plataforma, com nove módulos — os próximos passos visitam cada um.",
  },
  {
    tourId: "nav:/prospeccao",
    titulo: "Predator — Prospecção",
    descricao:
      "Crie um ICP (segmento, porte, região, CNAEs), gere uma lista de contas que batem com ele direto na base da Receita Federal, enriqueça cada conta (site + decisores via IA), ou importe uma Lista de Prospecção via planilha.",
    grupoToggle: "predator",
  },
  {
    tourId: "nav:/cadencias",
    titulo: "Predator — Cadências",
    descricao:
      "Sequências de toques multicanal (e-mail, WhatsApp, LinkedIn) escritas por IA — crie, gere as mensagens, aprove em Aprovações e só depois ative pra disparar.",
    grupoToggle: "predator",
  },
  {
    tourId: "nav:/campanhas",
    titulo: "Predator — Campanhas",
    descricao: "Disparo de e-mail/WhatsApp em massa pra uma lista, fora do fluxo de cadência de toques.",
    grupoToggle: "predator",
  },
  {
    tourId: "nav:/aprovacoes",
    titulo: "Predator — Aprovações",
    descricao:
      "Toda mensagem que a IA escreve passa por aqui antes de ser enviada — aprove, edite ou rejeite, com filtro por status.",
    grupoToggle: "predator",
  },
  {
    tourId: "nav:/reunioes",
    titulo: "Predator — Reuniões",
    descricao: "Lembretes automáticos e vídeo/transcrição das reuniões marcadas com seus prospects.",
    grupoToggle: "predator",
  },
  {
    tourId: "nav:/relatorio-entrega",
    titulo: "Predator — Relatório de Entrega",
    descricao:
      "Taxa de abertura/clique/resposta de e-mail e WhatsApp, com bloqueio automático de contatos com muito bounce.",
    grupoToggle: "predator",
  },
  {
    tourId: "nav:/regras-aprendidas",
    titulo: "Predator — Regras Aprendidas",
    descricao:
      "Cadastre regras de estilo/conteúdo que entram sozinhas no prompt da próxima cadência — a IA pode sugerir o texto a partir de uma correção recente sua.",
    grupoToggle: "predator",
  },
  {
    tourId: "nav:/inteligencia-rede",
    titulo: "Predator — Sinais de Oportunidade",
    descricao: "Fit de ICP contra a rede Shoal, matches de necessidades declaradas e riscos de pipeline — sempre com o motivo explicado.",
    grupoToggle: "predator",
  },
  {
    tourId: "nav:/agente-corporativo",
    titulo: "Predator — Agente Corporativo",
    descricao:
      "Um assistente de IA que responde, sob revisão humana, perguntas que outras empresas do Shoal fazem sobre a sua.",
    grupoToggle: "predator",
  },
  {
    tourId: "nav:/configuracao",
    titulo: "Predator — Configuração",
    descricao:
      "Oferta e tom de comunicação usados pela IA, conexões de WhatsApp/E-mail/LinkedIn (obrigatórias pra disparar), e modelo de proposta.",
    grupoToggle: "predator",
  },
  {
    tourId: "nav:/rede-social",
    titulo: "Shoal — a rede social B2B",
    descricao:
      "Camada gratuita da plataforma — funciona mesmo sem licença ativa do Predator. Os próximos passos visitam cada área.",
  },
  {
    tourId: "nav:/rede-social",
    titulo: "Shoal — Perfil e Verificação",
    descricao:
      "Logo, capa, setor, porte, mercados, produtos/serviços e certificações da sua empresa. Solicite verificação com um e-mail corporativo pra ganhar o selo.",
  },
  {
    tourId: "nav:/rede-social",
    titulo: "Shoal — Diretório e Conexões",
    descricao:
      "Busque empresas por setor/porte/mercado, conecte-se (com aceite mútuo) ou siga sem aceite; bloqueie ou desconecte quando precisar.",
  },
  {
    tourId: "nav:/rede-social",
    titulo: "Shoal — Mensagens e Salas Corporativas",
    descricao:
      "Converse por DM com uma empresa conectada, ou abra uma Sala Corporativa com canais (Geral, Comercial, Técnico...) pra assuntos mais estruturados.",
  },
  {
    tourId: "nav:/rede-social",
    titulo: "Shoal — Feed da Rede",
    descricao:
      "Publique posts com legenda, carrossel de fotos ou vídeo; comente, reaja (9 emojis) e compartilhe o que outras empresas publicam.",
  },
  {
    tourId: "nav:/rede-social",
    titulo: "Shoal — Necessidades da Rede",
    descricao:
      "Publique o que sua empresa está procurando (categoria, requisitos, orçamento) pra rede toda ou só suas conexões verem.",
  },
  {
    tourId: "nav:/rede-social",
    titulo: "Shoal — Convidar Empresa",
    descricao:
      "Gere um link pra uma empresa nova entrar no Shoal — qualquer pessoa da sua empresa pode gerar (o convite gratuito/cortesia é restrito a Admin/Super Admin).",
  },
  {
    tourId: "leads",
    titulo: "Leads",
    descricao: "Empresas e Contatos cadastrados diretamente, fora do fluxo de ICP.",
  },
  {
    tourId: "admin",
    titulo: "Admin",
    descricao:
      "Gestão de tenants/licenças/relatórios (hierarquia), Convites (traz um colega pro seu próprio tenant — qualquer Admin já pode gerar) e Planos/Verificações (Super Admin) — visível conforme o seu papel.",
  },
];

interface TourGuiadoProps {
  open: boolean;
  onClose: () => void;
}

function elementoDoPasso(tourId: string): HTMLElement | null {
  return document.querySelector(`[data-tour-id="${tourId}"]`);
}

function toggleDoGrupo(grupoToggle: string): HTMLButtonElement | null {
  return document.querySelector<HTMLButtonElement>(`[data-tour-toggle="${grupoToggle}"]`);
}

// Um passo com `grupoToggle` conta como "disponível" mesmo com o item
// ainda fora do DOM (grupo recolhido) — só fica indisponível de verdade
// se nem o BOTÃO de abrir o grupo existir (ex.: sem licença ativa,
// PREDATOR nem aparece no menu pra este usuário).
function passoDisponivel(passo: PassoTour): boolean {
  if (elementoDoPasso(passo.tourId) !== null) return true;
  return passo.grupoToggle !== undefined && toggleDoGrupo(passo.grupoToggle) !== null;
}

export function TourGuiado({ open, onClose }: TourGuiadoProps) {
  const [indice, setIndice] = useState(0);
  const [passos, setPassos] = useState<PassoTour[]>([]);
  const [retangulo, setRetangulo] = useState<DOMRect | null>(null);

  useEffect(() => {
    if (!open) return;
    setIndice(0);
    setPassos(PASSOS_TOUR.filter(passoDisponivel));
  }, [open]);

  const passoAtual = passos[indice];

  useEffect(() => {
    if (!passoAtual) return;
    let cancelado = false;
    function medir(elemento: Element) {
      if (cancelado) return;
      elemento.scrollIntoView({ block: "nearest" });
      setRetangulo(elemento.getBoundingClientRect());
    }
    function atualizarPosicao() {
      const elemento = elementoDoPasso(passoAtual.tourId);
      if (elemento) {
        medir(elemento);
        return;
      }
      // Item ainda não está no DOM (grupo PREDATOR recolhido) — abre o
      // grupo e dá um instante pro React re-renderizar antes de reler.
      if (passoAtual.grupoToggle) {
        toggleDoGrupo(passoAtual.grupoToggle)?.click();
        setTimeout(() => {
          if (cancelado) return;
          const reveladoAgora = elementoDoPasso(passoAtual.tourId);
          if (reveladoAgora) medir(reveladoAgora);
        }, 60);
        return;
      }
      setRetangulo(null);
    }
    atualizarPosicao();
    window.addEventListener("resize", atualizarPosicao);
    return () => {
      cancelado = true;
      window.removeEventListener("resize", atualizarPosicao);
    };
  }, [passoAtual]);

  useEffect(() => {
    if (!open) return;
    function aoTeclar(evento: KeyboardEvent) {
      if (evento.key === "Escape") onClose();
    }
    window.addEventListener("keydown", aoTeclar);
    return () => window.removeEventListener("keydown", aoTeclar);
  }, [open, onClose]);

  if (!open || !passoAtual || !retangulo) return null;

  const ultimoPasso = indice === passos.length - 1;
  const topoBalao = Math.min(retangulo.bottom + 12, window.innerHeight - 220);
  const esquerdaBalao = Math.min(retangulo.right + 12, window.innerWidth - 300);

  return (
    <div className="fixed inset-0 z-[60]">
      <div className="absolute inset-0 bg-slate-950/70" onClick={onClose} />
      <div
        className="pointer-events-none absolute rounded-lg ring-2 ring-cyan transition-all duration-200"
        style={{
          top: retangulo.top - 4,
          left: retangulo.left - 4,
          width: retangulo.width + 8,
          height: retangulo.height + 8,
        }}
      />
      <div
        className="absolute w-72 rounded-xl border border-border2 bg-surf p-4 shadow-xl transition-all duration-200"
        style={{ top: topoBalao, left: esquerdaBalao }}
      >
        <div className="mb-1 text-[10px] tracking-wide text-muted uppercase">
          Passo {indice + 1} de {passos.length}
        </div>
        <div className="mb-2 font-head text-sm font-bold text-text">{passoAtual.titulo}</div>
        <p className="mb-3 text-[12px] text-muted">{passoAtual.descricao}</p>
        <div className="flex items-center justify-between gap-2">
          <button type="button" onClick={onClose} className="text-[11px] text-muted hover:text-text">
            Pular tour
          </button>
          <button
            type="button"
            onClick={() =>
              setIndice((atual) => {
                if (atual >= passos.length - 1) {
                  onClose();
                  return atual;
                }
                return atual + 1;
              })
            }
            className="rounded-lg bg-cyan px-3 py-1.5 text-[12px] font-bold text-bg"
          >
            {ultimoPasso ? "Concluir" : "Próximo →"}
          </button>
        </div>
      </div>
    </div>
  );
}
