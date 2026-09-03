import { useEffect, useState } from "react";

// Um passo por módulo do menu lateral (raio-X 2026-09-01) — não
// clique-a-clique em cada ação de cada tela (escopo confirmado com o
// usuário: dúvidas mais específicas ficam pra FAQ com IA). Cada
// `tourId` casa com um `data-tour-id` marcado em AppShell.tsx; passos
// cujo elemento não existe no DOM no momento (ex.: "admin" pra quem não
// gerencia hierarquia) são pulados automaticamente.
interface PassoTour {
  tourId: string;
  titulo: string;
  descricao: string;
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
      "Seu quadro Kanban de negócios — arraste oportunidades entre os estágios do funil e gere propostas comerciais a partir de um negócio.",
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
      "Agrupa Prospecção (gerar listas por ICP e enriquecer contas), Cadências (sequências automáticas de toques), Campanhas (disparo em massa), Aprovações (revisar mensagens da IA antes de enviar), Reuniões e Configuração.",
  },
  {
    tourId: "rede-social",
    titulo: "Rede Social",
    descricao: "Seu perfil de empresa e convites para outras empresas entrarem na Rede Social B2B ON.",
  },
  {
    tourId: "leads",
    titulo: "Leads",
    descricao: "Empresas e Contatos cadastrados diretamente, fora do fluxo de ICP.",
  },
  {
    tourId: "admin",
    titulo: "Admin",
    descricao: "Gestão de tenants, licenças, relatórios, convites e planos — visível conforme o seu papel.",
  },
];

interface TourGuiadoProps {
  open: boolean;
  onClose: () => void;
}

function elementoDoPasso(tourId: string): HTMLElement | null {
  return document.querySelector(`[data-tour-id="${tourId}"]`);
}

export function TourGuiado({ open, onClose }: TourGuiadoProps) {
  const [indice, setIndice] = useState(0);
  const [passos, setPassos] = useState<PassoTour[]>([]);
  const [retangulo, setRetangulo] = useState<DOMRect | null>(null);

  useEffect(() => {
    if (!open) return;
    setIndice(0);
    setPassos(PASSOS_TOUR.filter((passo) => elementoDoPasso(passo.tourId) !== null));
  }, [open]);

  const passoAtual = passos[indice];

  useEffect(() => {
    if (!passoAtual) return;
    function atualizarPosicao() {
      const elemento = elementoDoPasso(passoAtual.tourId);
      setRetangulo(elemento ? elemento.getBoundingClientRect() : null);
    }
    atualizarPosicao();
    window.addEventListener("resize", atualizarPosicao);
    return () => window.removeEventListener("resize", atualizarPosicao);
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
