import { useEffect, useState } from "react";

import { api } from "@/lib/api";

interface LinhaPlano {
  plano: string;
  modo: "franquia_fixa" | "poc_autorizada" | "sob_consulta";
  franquia_creditos?: number;
  periodicidade?: string;
  limite_creditos_pesquisa?: number;
  decisores_por_empresa_max?: number;
  descricao?: string;
}

interface PacotePublico {
  codigo: string;
  nome: string;
  creditos: number | null;
  preco_unitario_brl: string | null;
  preco_total_brl: string | null;
  sob_negociacao: boolean;
}

interface Resposta {
  planos: LinhaPlano[];
  pacotes: PacotePublico[];
  observacoes: string[];
}

function reais(valor: string | null): string {
  return valor === null ? "—" : `R$ ${Number(valor).toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

/** Franquias de enriquecimento (pesquisa de decisores) por plano e pacotes adicionais. Dados vindos do servidor: a matriz aprovada e o catálogo
 * vigente. Não mostra mensalidade (a matriz não define preço de plano), custo nem margem. */
export function SecaoEnriquecimento() {
  const [dados, setDados] = useState<Resposta | null>(null);

  useEffect(() => {
    api.get<Resposta>("/planos/enriquecimento").then(setDados).catch(() => setDados(null));
  }, []);

  if (!dados) return null;

  return (
    <section className="mt-12" aria-labelledby="enriquecimento-titulo">
      <div className="mb-6 text-center">
        <div className="text-[10px] font-semibold tracking-widest text-cyan uppercase">Pesquisa de decisores</div>
        <h2 id="enriquecimento-titulo" className="mt-1.5 font-head text-xl font-bold text-text">
          Créditos de enriquecimento
        </h2>
        <p className="mx-auto mt-1.5 max-w-2xl text-[12.5px] text-muted">
          Cada plano inclui uma franquia mensal para buscar decisores de empresas que você escolhe. Você vê a estimativa antes de confirmar e nada é consultado sem a sua
          confirmação.
        </p>
      </div>

      <div className="overflow-x-auto rounded-xl border border-border bg-surf">
        <table className="w-full border-collapse text-[12.5px]">
          <thead>
            <tr className="border-b border-border text-[10px] tracking-wide text-muted uppercase">
              <th scope="col" className="p-3 text-left">Plano</th>
              <th scope="col" className="p-3 text-right">Franquia mensal</th>
              <th scope="col" className="p-3 text-right">Créditos por pesquisa</th>
              <th scope="col" className="p-3 text-right">Decisores por empresa</th>
            </tr>
          </thead>
          <tbody>
            {dados.planos.map((p) => (
              <tr key={p.plano} className="border-b border-border last:border-b-0">
                <th scope="row" className="p-3 text-left font-semibold text-text">{p.plano}</th>
                {p.modo === "franquia_fixa" ? (
                  <>
                    <td className="p-3 text-right tabular-nums">{p.franquia_creditos} créditos</td>
                    <td className="p-3 text-right tabular-nums">até {p.limite_creditos_pesquisa}</td>
                    <td className="p-3 text-right tabular-nums">até {p.decisores_por_empresa_max}</td>
                  </>
                ) : (
                  <td colSpan={3} className="p-3 text-right text-muted">
                    {p.descricao}
                    {p.modo === "poc_autorizada" ? " 1 decisor por empresa." : ""}
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="mt-8 mb-3 text-center">
        <h3 className="font-head text-[15px] font-bold text-text">Créditos adicionais</h3>
        <p className="mt-0.5 text-[12px] text-muted">Para quando a franquia do mês não bastar. Quanto maior o pacote, menor o preço por crédito.</p>
      </div>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-5">
        {dados.pacotes.map((p) => (
          <div key={p.codigo} className="flex flex-col gap-1 rounded-xl border border-border bg-surf p-4">
            <div className="font-head text-[14px] font-bold text-text">{p.nome}</div>
            {p.sob_negociacao ? (
              <div className="text-[12px] text-muted">Sob negociação com o time comercial.</div>
            ) : (
              <>
                <div className="font-head text-[20px] font-extrabold text-text tabular-nums">{reais(p.preco_total_brl)}</div>
                <div className="text-[12px] text-muted">{reais(p.preco_unitario_brl)} por crédito</div>
              </>
            )}
          </div>
        ))}
      </div>
      <ul className="mx-auto mt-4 max-w-3xl list-disc space-y-1 pl-5 text-[12px] text-muted">
        {dados.observacoes.map((o) => (
          <li key={o}>{o}</li>
        ))}
      </ul>
    </section>
  );
}
