import { useEffect, useState } from "react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { Card, SectionLabel } from "@/components/ui/Card";
import { KpiCard } from "@/components/ui/KpiCard";
import { api } from "@/lib/api";

interface MetricaNorte {
  mes_atual: string;
  valor_mes_atual: number;
  meta: number | null;
  valor_mes_anterior: number;
  variacao_percentual: number | null;
}

interface EstagioFunilResumo {
  estagio_id: number;
  nome: string;
  tipo: string;
  quantidade: number;
  valor_total: number;
}

interface DashboardFunil {
  periodo_inicio: string;
  periodo_fim: string;
  estagios: EstagioFunilResumo[];
  taxa_conversao: number | null;
}

interface DashboardEconomia {
  periodo: string;
  ltv_medio: number | null;
  cac: number | null;
  taxa_churn: number | null;
  novos_clientes: number;
  clientes_ativos_inicio_periodo: number;
  clientes_cancelados_periodo: number;
  roi: number | null;
  cs_score: number | null;
  nps_medio: number | null;
}

function formatarMoeda(valor: number | null): string {
  if (valor === null) return "—";
  return `R$${Math.round(valor / 1000)}k`;
}

function formatarPercentual(valor: number | null): string {
  if (valor === null) return "—";
  return `${(valor * 100).toFixed(1)}%`;
}

export function Dashboard() {
  const [metricaNorte, setMetricaNorte] = useState<MetricaNorte | null>(null);
  const [funil, setFunil] = useState<DashboardFunil | null>(null);
  const [economia, setEconomia] = useState<DashboardEconomia | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => {
    const periodoAtual = new Date().toISOString().slice(0, 7);
    Promise.all([
      api.get<MetricaNorte>("/painel/metrica-norte"),
      api.get<DashboardFunil>("/crm/dashboard/funil"),
      api.get<DashboardEconomia>(`/crm/dashboard/economia?periodo=${periodoAtual}`),
    ])
      .then(([metricaNorteResp, funilResp, economiaResp]) => {
        setMetricaNorte(metricaNorteResp);
        setFunil(funilResp);
        setEconomia(economiaResp);
      })
      .catch(() => setErro("Não foi possível carregar os dados do dashboard."));
  }, []);

  return (
    <div className="p-5.5">
      <div className="mb-5">
        <div className="font-head text-xl font-bold">Dashboard</div>
        <div className="mt-0.5 text-[11px] text-muted">Visão geral · CRM + MAP</div>
      </div>

      {erro && <div className="mb-4 text-[12px] text-red">{erro}</div>}

      <div className="mb-4 grid grid-cols-2 gap-2.5 sm:grid-cols-3">
        <KpiCard
          label="Reuniões qualificadas"
          value={metricaNorte?.valor_mes_atual ?? "—"}
          sub={metricaNorte ? `mês ${metricaNorte.mes_atual}` : undefined}
          colorClassName="text-cyan"
        />
        <KpiCard
          label="Variação vs mês anterior"
          value={metricaNorte?.variacao_percentual != null ? `${metricaNorte.variacao_percentual.toFixed(0)}%` : "—"}
          colorClassName="text-amber"
        />
        <KpiCard label="LTV médio" value={formatarMoeda(economia?.ltv_medio ?? null)} colorClassName="text-green" />
        <KpiCard label="CAC" value={formatarMoeda(economia?.cac ?? null)} colorClassName="text-red" />
        <KpiCard
          label="ROI (LTV/CAC)"
          value={economia?.roi != null ? `${economia.roi.toFixed(1)}x` : "—"}
          colorClassName="text-violet"
        />
        <KpiCard
          label="CS Score"
          value={economia?.cs_score != null ? economia.cs_score.toFixed(0) : "—"}
          sub={economia?.nps_medio != null ? `NPS médio ${economia.nps_medio.toFixed(1)}` : undefined}
          colorClassName="text-cyan"
        />
      </div>

      <div className="mb-4 grid grid-cols-1 gap-3.5 lg:grid-cols-2">
        <Card glow>
          <SectionLabel>Funil de vendas — negócios por estágio</SectionLabel>
          <div style={{ height: 220 }}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={funil?.estagios ?? []}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
                <XAxis dataKey="nome" tick={{ fill: "var(--color-muted)", fontSize: 10 }} />
                <YAxis tick={{ fill: "var(--color-muted)", fontSize: 10 }} allowDecimals={false} />
                <Tooltip
                  contentStyle={{ background: "var(--color-surf2)", border: "1px solid var(--color-border)" }}
                  labelStyle={{ color: "var(--color-text)" }}
                />
                <Bar dataKey="quantidade" name="Negócios" fill="var(--color-cyan)" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
          {funil?.taxa_conversao != null && (
            <div className="mt-2 text-[11px] text-muted">
              Taxa de conversão: <span className="text-cyan">{formatarPercentual(funil.taxa_conversao)}</span>
            </div>
          )}
        </Card>

        <Card>
          <SectionLabel>Economia — churn e carteira</SectionLabel>
          <div className="grid grid-cols-2 gap-2.5">
            <KpiCard
              label="Taxa de churn"
              value={formatarPercentual(economia?.taxa_churn ?? null)}
              colorClassName="text-amber"
            />
            <KpiCard label="Novos clientes" value={economia?.novos_clientes ?? "—"} colorClassName="text-green" />
            <KpiCard
              label="Clientes ativos"
              value={economia?.clientes_ativos_inicio_periodo ?? "—"}
              colorClassName="text-cyan"
            />
            <KpiCard
              label="Cancelamentos"
              value={economia?.clientes_cancelados_periodo ?? "—"}
              colorClassName="text-red"
            />
          </div>
        </Card>
      </div>
    </div>
  );
}
