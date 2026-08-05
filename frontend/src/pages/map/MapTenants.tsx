import { useEffect, useState, type FormEvent } from "react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, SectionLabel } from "@/components/ui/Card";
import { Input, Select } from "@/components/ui/Input";
import { KpiCard } from "@/components/ui/KpiCard";
import { Modal } from "@/components/ui/Modal";
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

interface ScoreRisco {
  tenant_id: string;
  score: number;
  classificacao: string;
  dias_sem_contato: number | null;
  sinais: Record<string, number>;
}

interface InteracaoTenant {
  id: number;
  tipo: string;
  descricao: string | null;
  criado_em: string;
}

interface ScriptResgate {
  script: string;
  justificativa: string;
}

const TIPOS_INTERACAO = [
  { valor: "contato", rotulo: "Contato" },
  { valor: "ticket_suporte", rotulo: "Ticket de Suporte" },
  { valor: "reclamacao", rotulo: "Reclamação" },
  { valor: "feedback_positivo", rotulo: "Feedback Positivo" },
  { valor: "reuniao_remarcada", rotulo: "Reunião Remarcada" },
  { valor: "mencionou_concorrente", rotulo: "Mencionou Concorrente" },
];

function toneClassificacao(classificacao: string): "red" | "amber" | "green" | "muted" {
  if (classificacao === "critico") return "red";
  if (classificacao === "atencao") return "amber";
  if (classificacao === "saudavel") return "green";
  return "muted";
}

/** Visão do super_admin — saúde dos tenants ASSINANTES da B2B ON
 * (cross-tenant). Distinta de MapContas.tsx, que é a saúde das contas
 * DENTRO de um tenant, vista por vendedor/gestor. */
export function MapTenants() {
  const [dashboard, setDashboard] = useState<DashboardMotor | null>(null);
  const [ranking, setRanking] = useState<SaudeTenant[]>([]);
  const [tenantSelecionado, setTenantSelecionado] = useState<string | null>(null);
  const [scoreRisco, setScoreRisco] = useState<ScoreRisco | null>(null);
  const [interacoes, setInteracoes] = useState<InteracaoTenant[]>([]);
  const [script, setScript] = useState<ScriptResgate | null>(null);
  const [modalInteracaoAberto, setModalInteracaoAberto] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [gerandoScript, setGerandoScript] = useState(false);

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

  async function carregarDetalheTenant(tenantId: string) {
    setScript(null);
    try {
      const [scoreResp, interacoesResp] = await Promise.all([
        api.get<ScoreRisco>(`/motor/tenants/${tenantId}/score-risco`),
        api.get<InteracaoTenant[]>(`/motor/tenants/${tenantId}/interacoes`),
      ]);
      setScoreRisco(scoreResp);
      setInteracoes(interacoesResp);
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível carregar o detalhe do tenant.");
    }
  }

  useEffect(() => {
    carregarVisaoGeral();
  }, []);

  useEffect(() => {
    if (tenantSelecionado) carregarDetalheTenant(tenantSelecionado);
  }, [tenantSelecionado]);

  async function registrarInteracao(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!tenantSelecionado) return;
    const form = new FormData(event.currentTarget);
    try {
      await api.post("/motor/interacoes", {
        tenant_id: tenantSelecionado,
        tipo: String(form.get("tipo")),
        descricao: String(form.get("descricao") || "") || null,
      });
      setModalInteracaoAberto(false);
      await Promise.all([carregarDetalheTenant(tenantSelecionado), carregarVisaoGeral()]);
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível registrar a interação.");
    }
  }

  async function gerarScript() {
    if (!tenantSelecionado) return;
    setGerandoScript(true);
    try {
      setScript(await api.get<ScriptResgate>(`/motor/tenants/${tenantSelecionado}/script-resgate`));
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível gerar o script de resgate.");
    } finally {
      setGerandoScript(false);
    }
  }

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

          {tenantSelecionado && scoreRisco && (
            <>
              <div className="mb-3 flex items-center gap-2">
                <Badge tone={toneClassificacao(scoreRisco.classificacao)}>
                  {scoreRisco.classificacao} · {scoreRisco.score.toFixed(0)}/100
                </Badge>
                {scoreRisco.dias_sem_contato !== null && (
                  <span className="text-[11px] text-muted">{scoreRisco.dias_sem_contato}d sem contato</span>
                )}
              </div>

              {Object.keys(scoreRisco.sinais).length > 0 && (
                <div className="mb-3 text-[11px] text-muted">
                  {Object.entries(scoreRisco.sinais).map(([sinal, pontos]) => (
                    <div key={sinal}>
                      {sinal}: {pontos > 0 ? "+" : ""}
                      {pontos}
                    </div>
                  ))}
                </div>
              )}

              <div className="mb-3 flex gap-2">
                <Button size="sm" onClick={() => setModalInteracaoAberto(true)}>
                  Registrar interação
                </Button>
                <Button size="sm" variant="amber" disabled={gerandoScript} onClick={gerarScript}>
                  {gerandoScript ? "Gerando..." : "Gerar script de resgate"}
                </Button>
              </div>

              {script && (
                <div className="mb-3 rounded-lg border border-border bg-surf2 p-3 text-[12px] leading-relaxed whitespace-pre-wrap">
                  {script.script}
                  <div className="mt-2 border-t border-border pt-2 text-[11px] text-muted">
                    {script.justificativa}
                  </div>
                  <Button
                    size="sm"
                    variant="ghost"
                    className="mt-2"
                    onClick={() => navigator.clipboard.writeText(script.script)}
                  >
                    Copiar
                  </Button>
                </div>
              )}

              <div>
                <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">Histórico de interações</div>
                <div className="flex flex-col gap-1 text-[11px]">
                  {interacoes.map((interacao) => (
                    <div key={interacao.id} className="border-b border-border py-1">
                      <span className="font-semibold text-text">{interacao.tipo}</span>
                      {interacao.descricao && <span className="text-muted"> — {interacao.descricao}</span>}
                    </div>
                  ))}
                  {interacoes.length === 0 && <div className="text-muted">Nenhuma interação registrada.</div>}
                </div>
              </div>
            </>
          )}
        </Card>
      </div>

      <Modal
        title="Registrar interação"
        open={modalInteracaoAberto}
        onClose={() => setModalInteracaoAberto(false)}
      >
        <form onSubmit={registrarInteracao} className="flex flex-col gap-3">
          <div>
            <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">Tipo</div>
            <Select name="tipo" required defaultValue="">
              <option value="" disabled>
                Selecione...
              </option>
              {TIPOS_INTERACAO.map((tipo) => (
                <option key={tipo.valor} value={tipo.valor}>
                  {tipo.rotulo}
                </option>
              ))}
            </Select>
          </div>
          <div>
            <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">Descrição (opcional)</div>
            <Input name="descricao" />
          </div>
          <Button type="submit" className="w-full justify-center">
            Registrar
          </Button>
        </form>
      </Modal>
    </div>
  );
}
