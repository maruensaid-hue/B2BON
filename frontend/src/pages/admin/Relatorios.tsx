import { useEffect, useState, type FormEvent } from "react";

import { Button } from "@/components/ui/Button";
import { Card, SectionLabel } from "@/components/ui/Card";
import { Select } from "@/components/ui/Input";
import { KpiCard } from "@/components/ui/KpiCard";
import { AcessoRestrito } from "@/pages/admin/AcessoRestrito";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";

interface Metricas {
  periodo_inicio: string;
  periodo_fim: string;
  tenants_ativos_distribuidor: number;
  tenants_ativos_revendedor: number;
  tenants_ativos_cliente: number;
  novas_ativacoes: number;
  licencas_suspensas_periodo: number;
  licencas_suspensas_total: number;
  franquia_limite_total: number;
  franquia_usado_total: number;
  receita_periodo: number;
  churn_atual: number;
}

interface DashboardRelatorio {
  atual: Metricas;
  anterior: Metricas;
}

interface ConfiguracaoRelatorio {
  cadencia: string;
  ultimo_envio_em: string | null;
}

function variacao(atual: number, anterior: number): string | undefined {
  if (anterior === 0) return undefined;
  const percentual = ((atual - anterior) / anterior) * 100;
  const sinal = percentual >= 0 ? "+" : "";
  return `${sinal}${percentual.toFixed(0)}% vs. período anterior`;
}

export function Relatorios() {
  const { usuario } = useAuth();
  const [dashboard, setDashboard] = useState<DashboardRelatorio | null>(null);
  const [config, setConfig] = useState<ConfiguracaoRelatorio | null>(null);
  const [periodoDias, setPeriodoDias] = useState(7);
  const [erro, setErro] = useState<string | null>(null);

  const podeGerenciar =
    usuario?.papel === "super_admin" ||
    (usuario?.papel === "admin" && ["distribuidor", "revendedor"].includes(usuario.tenant_tipo));

  async function carregar() {
    try {
      setDashboard(await api.get<DashboardRelatorio>(`/relatorios/dashboard?periodo_dias=${periodoDias}`));
    } catch {
      setErro("Não foi possível carregar o relatório.");
    }
    try {
      setConfig(await api.get<ConfiguracaoRelatorio>("/relatorios/configuracao"));
    } catch {
      setConfig(null);
    }
  }

  useEffect(() => {
    if (podeGerenciar) carregar();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [podeGerenciar, periodoDias]);

  async function salvarCadencia(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    try {
      await api.put("/relatorios/configuracao", { cadencia: String(form.get("cadencia")) });
      await carregar();
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível salvar a cadência.");
    }
  }

  if (!podeGerenciar) return <AcessoRestrito />;

  const m = dashboard?.atual;
  const a = dashboard?.anterior;
  const tenantsAtivos = m ? m.tenants_ativos_distribuidor + m.tenants_ativos_revendedor + m.tenants_ativos_cliente : 0;
  const tenantsAtivosAnterior = a ? a.tenants_ativos_distribuidor + a.tenants_ativos_revendedor + a.tenants_ativos_cliente : 0;

  return (
    <div className="p-5.5">
      <div className="mb-5 flex items-end justify-between">
        <div>
          <div className="font-head text-xl font-bold">Relatórios</div>
          <div className="mt-0.5 text-[11px] text-muted">Volumetria, franquia, inadimplência e receita da sua árvore</div>
        </div>
        <Select value={periodoDias} onChange={(e) => setPeriodoDias(Number(e.target.value))} className="w-auto">
          <option value={7}>Últimos 7 dias</option>
          <option value={30}>Últimos 30 dias</option>
          <option value={90}>Últimos 90 dias</option>
        </Select>
      </div>

      {erro && <div className="mb-4 text-[12px] text-red">{erro}</div>}

      <div className="mb-4 grid grid-cols-2 gap-2.5 sm:grid-cols-3">
        <KpiCard
          label="Tenants ativos"
          value={m ? tenantsAtivos : "—"}
          sub={m ? `${m.tenants_ativos_distribuidor} distrib. · ${m.tenants_ativos_revendedor} revend. · ${m.tenants_ativos_cliente} cliente` : undefined}
          colorClassName="text-cyan"
        />
        <KpiCard
          label="Novas ativações"
          value={m?.novas_ativacoes ?? "—"}
          sub={m && a ? variacao(m.novas_ativacoes, a.novas_ativacoes) : undefined}
          colorClassName="text-green"
        />
        <KpiCard
          label="Suspensas no período"
          value={m?.licencas_suspensas_periodo ?? "—"}
          sub={m ? `${m.licencas_suspensas_total} suspensas no total` : undefined}
          colorClassName="text-amber"
        />
        <KpiCard
          label="Franquia usada"
          value={m ? `${m.franquia_usado_total}/${m.franquia_limite_total}` : "—"}
          colorClassName="text-violet"
        />
        <KpiCard
          label="Receita confirmada"
          value={m ? `R$${m.receita_periodo.toFixed(0)}` : "—"}
          sub={m && a ? variacao(m.receita_periodo, a.receita_periodo) : undefined}
          colorClassName="text-green"
        />
        <KpiCard
          label="Churn (suspenso há 30+ dias)"
          value={m?.churn_atual ?? "—"}
          colorClassName="text-red"
        />
      </div>

      {tenantsAtivosAnterior === 0 && m && (
        <div className="mb-4 text-[11px] text-muted">Sem dados do período anterior pra comparar ainda.</div>
      )}

      <Card>
        <SectionLabel>Cadência do relatório periódico</SectionLabel>
        <div className="mb-3 text-[11px] text-muted">
          Manda por e-mail (e, se você for Distribuidor, também dispara webhook) automaticamente nessa frequência.
        </div>
        <form onSubmit={salvarCadencia} className="flex items-center gap-2">
          <Select name="cadencia" defaultValue={config?.cadencia ?? "desativada"} className="w-auto">
            <option value="desativada">Desativada</option>
            <option value="diaria">Diária</option>
            <option value="semanal">Semanal</option>
            <option value="mensal">Mensal</option>
          </Select>
          <Button type="submit">Salvar</Button>
        </form>
        {config?.ultimo_envio_em && (
          <div className="mt-2 text-[11px] text-muted">
            Último envio: {new Date(config.ultimo_envio_em).toLocaleString("pt-BR")}
          </div>
        )}
      </Card>
    </div>
  );
}
