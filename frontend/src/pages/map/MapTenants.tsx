import { useEffect, useState } from "react";

import { Badge } from "@/components/ui/Badge";
import { Card, SectionLabel } from "@/components/ui/Card";
import { KpiCard } from "@/components/ui/KpiCard";
import { DetalheRisco } from "@/pages/map/DetalheRisco";
import { toneClassificacao } from "@/pages/map/risco";
import { api, ApiError } from "@/lib/api";

interface DashboardMotor {
  score_medio: number | null;
  total_tenants: number;
  criticos: number;
  atencao: number;
  saudaveis: number;
  valor_total_em_risco: number;
}

interface SaudeTenant {
  tenant_id: string;
  nome_exibicao: string;
  score: number;
  classificacao: "critico" | "atencao" | "saudavel";
  meses_como_cliente: number;
  valor_mensal: number;
  valor_em_risco: number;
}

/** Visão do super_admin — saúde dos tenants ASSINANTES da B2B ON
 * (cross-tenant). Distinta de MapContas.tsx, que é a saúde das contas
 * DENTRO de um tenant, vista por vendedor/gestor. */
export function MapTenants() {
  const [dashboard, setDashboard] = useState<DashboardMotor | null>(null);
  const [ranking, setRanking] = useState<SaudeTenant[]>([]);
  const [tenantSelecionado, setTenantSelecionado] = useState<string | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  async function carregarVisaoGeral() {
    try {
      const [dashboardResp, rankingResp] = await Promise.all([
        api.get<DashboardMotor>("/motor/dashboard"),
        api.get<SaudeTenant[]>("/motor/saude-tenants"),
      ]);
      setDashboard(dashboardResp);
      setRanking(rankingResp);
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível carregar o MAP.");
    }
  }

  useEffect(() => {
    carregarVisaoGeral();
  }, []);

  const tenantNome = ranking.find((item) => item.tenant_id === tenantSelecionado)?.nome_exibicao;

  return (
    <div className="p-5.5">
      <div className="mb-5">
        <div className="font-head text-xl font-bold">MAP — Motor de Alta Performance</div>
        <div className="mt-0.5 text-[11px] text-muted">Saúde e risco de churn dos tenants da B2B ON</div>
      </div>

      {erro && <div className="mb-4 text-[12px] text-red">{erro}</div>}

      <div className="mb-4 grid grid-cols-2 gap-2.5 sm:grid-cols-4">
        <KpiCard label="Score médio" value={dashboard?.score_medio?.toFixed(0) ?? "—"} colorClassName="text-cyan" />
        <KpiCard label="Críticos" value={dashboard?.criticos ?? "—"} colorClassName="text-red" />
        <KpiCard label="Atenção" value={dashboard?.atencao ?? "—"} colorClassName="text-amber" />
        <KpiCard
          label="Valor em risco"
          value={dashboard ? `R$${Math.round(dashboard.valor_total_em_risco / 1000)}k` : "—"}
          colorClassName="text-red"
        />
      </div>

      <div className="grid grid-cols-1 gap-3.5 lg:grid-cols-2">
        <Card>
          <SectionLabel>Ranking de saúde</SectionLabel>
          <table className="w-full border-collapse text-[12px]">
            <thead>
              <tr className="border-b border-border text-[9.5px] tracking-wide text-muted uppercase">
                <th className="p-2 text-left">Tenant</th>
                <th className="p-2 text-left">Score</th>
                <th className="p-2 text-left">Valor em risco</th>
              </tr>
            </thead>
            <tbody>
              {ranking.map((item) => (
                <tr
                  key={item.tenant_id}
                  onClick={() => setTenantSelecionado(item.tenant_id)}
                  className={`cursor-pointer border-b border-border ${
                    item.tenant_id === tenantSelecionado ? "bg-surf2" : ""
                  }`}
                >
                  <td className="p-2 font-semibold">{item.nome_exibicao}</td>
                  <td className="p-2">
                    <Badge tone={toneClassificacao(item.classificacao)}>{item.score.toFixed(0)}</Badge>
                  </td>
                  <td className="p-2 text-muted">R${Math.round(item.valor_em_risco / 1000)}k</td>
                </tr>
              ))}
              {ranking.length === 0 && (
                <tr>
                  <td colSpan={3} className="p-4 text-center text-muted">
                    Nenhum tenant cadastrado ainda.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </Card>

        <Card glow>
          <SectionLabel>{tenantNome ? `Detalhe — ${tenantNome}` : "Selecione um tenant no ranking"}</SectionLabel>

          {tenantSelecionado && (
            <DetalheRisco
              key={tenantSelecionado}
              base={`/motor/tenants/${tenantSelecionado}`}
              interacao={{ caminho: "/motor/interacoes", alvo: { tenant_id: tenantSelecionado } }}
              aoRegistrar={carregarVisaoGeral}
              aoErro={setErro}
            />
          )}
        </Card>
      </div>

    </div>
  );
}
