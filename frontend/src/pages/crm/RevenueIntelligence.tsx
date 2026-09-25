import { useEffect, useState } from "react";

import { Card, SectionLabel } from "@/components/ui/Card";
import { Select } from "@/components/ui/Input";
import { api, ApiError } from "@/lib/api";

interface Metrica {
  valor: number | null;
  unidade: "BRL" | "taxa" | "dias" | "nota" | "contratos";
  metodologia: string;
  amostra: number;
  [detalhe: string]: unknown;
}

type Metricas = Record<string, Metrica> & {
  periodo: { inicio: string; fim: string };
};

const ROTULOS: Record<string, string> = {
  network_sourced_pipeline: "Pipeline originado pela rede",
  network_influenced_pipeline: "Pipeline influenciado pela rede",
  ai_assisted_pipeline: "Pipeline assistido por IA",
  ai_assisted_revenue: "Receita assistida por IA",
  signal_conversion: "Conversão de sinais",
  intent_conversion: "Conversão de intenções",
  match_conversion: "Conversão de matches",
  offer_conversion: "Taxa de ganho por oferta",
  churn_prevention_value: "Valor preservado com ação anti-churn",
  contract_renewal_risk: "Contratos públicos a renovar (valor)",
};

function formatarMetrica(m: Metrica): string {
  if (m.valor === null || m.valor === undefined) return "—";
  if (m.unidade === "BRL")
    return m.valor.toLocaleString("pt-BR", {
      style: "currency",
      currency: "BRL",
    });
  if (m.unidade === "taxa")
    return `${(m.valor * 100).toLocaleString("pt-BR", { maximumFractionDigits: 1 })}%`;
  return m.valor.toLocaleString("pt-BR");
}

/** Revenue Intelligence (Fase 16): métricas do lado vendedor, cada uma com
 * a metodologia (o que conta) e a amostra. Atribuição não é causalidade. */
export function RevenueIntelligence() {
  const [dias, setDias] = useState(90);
  const [dados, setDados] = useState<Metricas | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => {
    const inicio = new Date(Date.now() - dias * 86_400_000).toISOString();
    api
      .get<Metricas>(
        `/inteligencia/receita/metricas?inicio=${encodeURIComponent(inicio)}`,
      )
      .then(setDados)
      .catch((error) =>
        setErro(
          error instanceof ApiError
            ? error.message
            : "Não foi possível carregar as métricas.",
        ),
      );
  }, [dias]);

  if (!dados)
    return (
      <div className="text-[12px] text-muted">{erro ?? "Carregando..."}</div>
    );
  const ofertas = (dados.offer_conversion?.por_oferta ?? []) as {
    oferta: string;
    ganhos: number;
    perdidos: number;
    taxa_ganho: number | null;
    valor_ganho: number;
  }[];

  return (
    <div className="flex flex-col gap-4" data-testid="revenue-intelligence">
      <div className="flex flex-wrap items-end justify-between gap-2">
        <div>
          <div className="font-head text-xl font-bold">
            Revenue Intelligence
          </div>
          <div className="text-[11px] text-muted">
            Pipeline é retrato de agora; receita e conversões são do período.
            Atribuição mostra toque registrado, não causalidade.
          </div>
        </div>
        <Select
          value={dias}
          onChange={(e) => setDias(Number(e.target.value))}
          className="w-40"
        >
          <option value={30}>Últimos 30 dias</option>
          <option value={90}>Últimos 90 dias</option>
          <option value={365}>Últimos 12 meses</option>
        </Select>
      </div>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {Object.keys(ROTULOS)
          .filter((chave) => dados[chave])
          .map((chave) => (
            <Card key={chave}>
              <SectionLabel>{ROTULOS[chave]}</SectionLabel>
              <div className="font-head text-2xl font-extrabold text-text">
                {formatarMetrica(dados[chave])}
              </div>
              <div className="mt-1 text-[10.5px] text-muted">
                Amostra: {dados[chave].amostra}
              </div>
              <div className="mt-1.5 text-[10.5px] leading-relaxed text-muted">
                {dados[chave].metodologia}
              </div>
            </Card>
          ))}
      </div>

      {ofertas.length > 0 && (
        <Card>
          <SectionLabel>Conversão por oferta</SectionLabel>
          <div className="flex flex-col gap-1 text-[12px]">
            {ofertas.map((o) => (
              <div key={o.oferta} className="flex justify-between gap-2">
                <span className="text-text">{o.oferta}</span>
                <span className="text-muted">
                  {o.ganhos} ganho(s) · {o.perdidos} perdido(s) ·{" "}
                  {o.taxa_ganho === null
                    ? "—"
                    : `${Math.round(o.taxa_ganho * 100)}%`}{" "}
                  ·{" "}
                  {o.valor_ganho.toLocaleString("pt-BR", {
                    style: "currency",
                    currency: "BRL",
                  })}
                </span>
              </div>
            ))}
          </div>
        </Card>
      )}
    </div>
  );
}
