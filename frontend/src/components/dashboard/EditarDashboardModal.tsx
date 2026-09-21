import { useEffect, useState } from "react";

import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import { api, ApiError } from "@/lib/api";

export interface PreferenciaDashboardItem {
  chave: string;
  visivel: boolean;
}

const NOMES_SECAO: Record<string, string> = {
  kpis_norte: "Indicadores (KPIs)",
  funil: "Funil de vendas",
  economia: "Economia — churn e carteira",
};

interface EditarDashboardModalProps {
  open: boolean;
  onClose: () => void;
  itens: PreferenciaDashboardItem[];
  onSalvo: (itens: PreferenciaDashboardItem[]) => void;
}

/** "Editar Dashboard" (redesign Salesforce, raio-X 2026-09-21) — reordena
 * e mostra/oculta as 3 seções da Dashboard, mesmo padrão de ▲▼ do "Editar
 * Funil" em Kanban.tsx. Granularidade de seção, não de card individual. */
export function EditarDashboardModal({ open, onClose, itens, onSalvo }: EditarDashboardModalProps) {
  const [locais, setLocais] = useState<PreferenciaDashboardItem[]>(itens);
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => {
    if (open) {
      setLocais(itens);
      setErro(null);
    }
  }, [open, itens]);

  function mover(indice: number, direcao: "cima" | "baixo") {
    const indiceAlvo = direcao === "cima" ? indice - 1 : indice + 1;
    if (indiceAlvo < 0 || indiceAlvo >= locais.length) return;
    const nova = [...locais];
    [nova[indice], nova[indiceAlvo]] = [nova[indiceAlvo], nova[indice]];
    setLocais(nova);
  }

  function alternarVisibilidade(indice: number) {
    setLocais((atual) => atual.map((item, i) => (i === indice ? { ...item, visivel: !item.visivel } : item)));
  }

  async function salvar() {
    setSalvando(true);
    setErro(null);
    try {
      const resposta = await api.put<PreferenciaDashboardItem[]>("/painel/preferencias-dashboard", {
        itens: locais,
      });
      onSalvo(resposta);
      onClose();
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível salvar a configuração da Dashboard.");
    } finally {
      setSalvando(false);
    }
  }

  return (
    <Modal title="Editar Dashboard" open={open} onClose={onClose}>
      <div className="flex flex-col gap-3">
        {erro && <div className="text-[12px] text-red">{erro}</div>}
        <div className="flex flex-col gap-2">
          {locais.map((item, indice) => (
            <div key={item.chave} className="flex items-center gap-2">
              <div className="flex flex-col">
                <button
                  type="button"
                  className="leading-none text-muted hover:text-cyan disabled:opacity-30"
                  onClick={() => mover(indice, "cima")}
                  disabled={indice === 0}
                  title="Mover para cima"
                >
                  ▲
                </button>
                <button
                  type="button"
                  className="leading-none text-muted hover:text-cyan disabled:opacity-30"
                  onClick={() => mover(indice, "baixo")}
                  disabled={indice === locais.length - 1}
                  title="Mover para baixo"
                >
                  ▼
                </button>
              </div>
              <span className={`flex-1 text-[12px] ${item.visivel ? "text-text" : "text-muted"}`}>
                {NOMES_SECAO[item.chave] ?? item.chave}
              </span>
              <label className="flex items-center gap-1.5 text-[11px] text-muted">
                <input type="checkbox" checked={item.visivel} onChange={() => alternarVisibilidade(indice)} />
                Visível
              </label>
            </div>
          ))}
        </div>
        <div className="mt-1 flex gap-2">
          <Button onClick={salvar} disabled={salvando}>
            {salvando ? "Salvando..." : "Salvar"}
          </Button>
          <Button variant="ghost" onClick={onClose} disabled={salvando}>
            Cancelar
          </Button>
        </div>
      </div>
    </Modal>
  );
}
