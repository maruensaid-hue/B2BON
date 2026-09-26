import type { ReactNode } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { cn } from "@/lib/cn";

export interface AbaWorkspace {
  id: string;
  rotulo: string;
  conteudo: ReactNode;
  /** Número exibido ao lado do rótulo (ex.: pendências). */
  contador?: number;
  /** Abas irrelevantes para o tipo de processo/papel não aparecem. */
  visivel?: boolean;
}

/** Workspace de processo compartilhado (plano unificado §28): mesma moldura
 * para licitação (vendedor) e processo de compra (comprador), com abas
 * configuradas por quem usa. A aba ativa fica na URL (`?aba=`) para link direto. */
export function ProcessWorkspace({
  voltar,
  titulo,
  subtitulo,
  avisos,
  abas,
  testId,
}: {
  voltar: { para: string; rotulo: string };
  titulo: ReactNode;
  subtitulo?: ReactNode;
  avisos?: ReactNode;
  abas: AbaWorkspace[];
  testId?: string;
}) {
  const [parametros, setParametros] = useSearchParams();
  const visiveis = abas.filter((aba) => aba.visivel !== false);
  const ativa =
    visiveis.find((aba) => aba.id === parametros.get("aba")) ?? visiveis[0];

  function abrir(id: string) {
    const proximos = new URLSearchParams(parametros);
    proximos.set("aba", id);
    setParametros(proximos, { replace: true });
  }

  return (
    <div className="flex flex-col gap-3.5" data-testid={testId}>
      <Link to={voltar.para} className="text-[11px] text-cyan">
        ← {voltar.rotulo}
      </Link>
      <div>
        <div className="font-head text-xl font-bold">{titulo}</div>
        {subtitulo && <div className="text-[11px] text-muted">{subtitulo}</div>}
      </div>
      {avisos}
      <div
        role="tablist"
        className="flex flex-wrap gap-1 border-b border-border text-[12px]"
      >
        {visiveis.map((aba) => (
          <button
            key={aba.id}
            type="button"
            role="tab"
            aria-selected={aba.id === ativa?.id}
            onClick={() => abrir(aba.id)}
            className={cn(
              "-mb-px border-b-2 px-3 py-1.5",
              aba.id === ativa?.id
                ? "border-cyan text-text"
                : "border-transparent text-muted hover:text-text",
            )}
          >
            {aba.rotulo}
            {aba.contador ? (
              <span className="ml-1 text-[10px] text-amber">
                ({aba.contador})
              </span>
            ) : null}
          </button>
        ))}
      </div>
      <div role="tabpanel">{ativa?.conteudo}</div>
    </div>
  );
}
