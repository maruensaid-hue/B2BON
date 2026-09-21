import { useEffect, useState } from "react";

/** Motor genérico de passo-a-passo (raio-X 2026-09-21) — extraído do
 * `TourGuiado.tsx` original pra ser reaproveitado tanto pelo tour grande
 * (menu, `data-tour-id`/`data-tour-toggle`) quanto pelos tutoriais por
 * módulo (`data-tutorial-id`/`data-tutorial-toggle`) — os atributos são
 * parametrizados via `atributoSeletor`/`atributoToggle` justamente pra
 * garantir que os dois sistemas nunca colidam, mesmo que um item de nav
 * e um elemento de módulo usem o mesmo id lógico por acaso. */
export interface PassoGuia {
  id: string;
  titulo: string;
  descricao: string;
  /** Só usado quando o elemento do passo ainda não está no DOM (ex.: um
   * grupo de menu recolhido, ou um modal ainda fechado) — clica no
   * elemento marcado com `atributoToggle=grupoToggle` pra revelá-lo. */
  grupoToggle?: string;
}

interface GuiaPassoAPassoProps {
  open: boolean;
  onClose: () => void;
  passos: PassoGuia[];
  atributoSeletor: string;
  atributoToggle: string;
}

export function GuiaPassoAPasso({ open, onClose, passos, atributoSeletor, atributoToggle }: GuiaPassoAPassoProps) {
  const [indice, setIndice] = useState(0);
  const [passosDisponiveis, setPassosDisponiveis] = useState<PassoGuia[]>([]);
  const [retangulo, setRetangulo] = useState<DOMRect | null>(null);

  function elementoDoPasso(id: string): HTMLElement | null {
    return document.querySelector(`[${atributoSeletor}="${id}"]`);
  }

  function toggleDoGrupo(grupoToggle: string): HTMLButtonElement | null {
    return document.querySelector<HTMLButtonElement>(`[${atributoToggle}="${grupoToggle}"]`);
  }

  // Um passo com `grupoToggle` conta como "disponível" mesmo com o item
  // ainda fora do DOM (grupo/modal fechado) — só fica indisponível de
  // verdade se nem o gatilho de abrir existir.
  function passoDisponivel(passo: PassoGuia): boolean {
    if (elementoDoPasso(passo.id) !== null) return true;
    return passo.grupoToggle !== undefined && toggleDoGrupo(passo.grupoToggle) !== null;
  }

  useEffect(() => {
    if (!open) return;
    setIndice(0);
    setPassosDisponiveis(passos.filter(passoDisponivel));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const passoAtual = passosDisponiveis[indice];

  useEffect(() => {
    if (!passoAtual) return;
    let cancelado = false;
    function medir(elemento: Element) {
      if (cancelado) return;
      elemento.scrollIntoView({ block: "nearest" });
      setRetangulo(elemento.getBoundingClientRect());
    }
    function atualizarPosicao() {
      const elemento = elementoDoPasso(passoAtual.id);
      if (elemento) {
        medir(elemento);
        return;
      }
      // Item ainda não está no DOM (grupo/modal fechado) — abre o
      // gatilho e dá um instante pro React re-renderizar antes de reler.
      if (passoAtual.grupoToggle) {
        toggleDoGrupo(passoAtual.grupoToggle)?.click();
        setTimeout(() => {
          if (cancelado) return;
          const reveladoAgora = elementoDoPasso(passoAtual.id);
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
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

  const ultimoPasso = indice === passosDisponiveis.length - 1;
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
          Passo {indice + 1} de {passosDisponiveis.length}
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
                if (atual >= passosDisponiveis.length - 1) {
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
