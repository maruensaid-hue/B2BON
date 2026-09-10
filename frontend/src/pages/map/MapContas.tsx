import { useEffect, useMemo, useState, type FormEvent } from "react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, SectionLabel } from "@/components/ui/Card";
import { Input, Select } from "@/components/ui/Input";
import { KpiCard } from "@/components/ui/KpiCard";
import { Modal } from "@/components/ui/Modal";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";

interface DashboardSaudeContas {
  score_medio: number | null;
  total_contas: number;
  criticas: number;
  atencao: number;
  saudaveis: number;
  valor_total_em_risco: number;
  roi: number | null;
  cs_score: number | null;
  nps_medio: number | null;
}

interface SaudeConta {
  conta_id: number;
  nome: string;
  nome_fantasia: string | null;
  tenant_id: string;
  tenant_nome: string;
  vendedor_usuario_id: number | null;
  vendedor_nome: string | null;
  score: number;
  classificacao: "critico" | "atencao" | "saudavel";
  valor_pipeline_aberto: number;
}

interface ScoreRiscoConta {
  conta_id: number;
  score: number;
  classificacao: string;
  dias_sem_contato: number | null;
  sinais: Record<string, number>;
}

interface InteracaoConta {
  id: number;
  tipo: string;
  descricao: string | null;
  criado_em: string;
}

interface ScriptResgateConta {
  script: string;
  justificativa: string;
}

interface UsuarioResumo {
  id: number;
  nome: string;
}

interface TenantResumo {
  id: string;
  razao_social: string;
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

/** Visão de user/admin — saúde das CONTAS (clientes/prospects) dentro do
 * próprio tenant. Vendedor (user) só vê a carteira dele; gestor (admin)
 * vê o time inteiro e pode filtrar por vendedor. Distinta de
 * MapTenants.tsx, exclusiva do super_admin. */
export function MapContas() {
  const { usuario } = useAuth();
  const isGestor = usuario?.papel === "admin" || usuario?.papel === "super_admin";
  const isSuperAdmin = usuario?.papel === "super_admin";
  // Mesma condição de AppShell.tsx/AdminTenants.tsx — quem gerencia mais
  // de um tenant (hierarquia de distribuidores, raio-X 2026-09-10).
  const ehGestorHierarquico =
    usuario?.papel === "admin" && ["distribuidor", "revendedor"].includes(usuario.tenant_tipo);
  const podeVerHierarquia = isSuperAdmin || ehGestorHierarquico;

  const [dashboard, setDashboard] = useState<DashboardSaudeContas | null>(null);
  const [ranking, setRanking] = useState<SaudeConta[]>([]);
  const [vendedores, setVendedores] = useState<UsuarioResumo[]>([]);
  const [tenantsVisiveis, setTenantsVisiveis] = useState<TenantResumo[]>([]);
  const [filtroVendedorId, setFiltroVendedorId] = useState<number | null>(null);
  const [tenantSelecionadoId, setTenantSelecionadoId] = useState<string | null>(null);
  const [busca, setBusca] = useState("");
  const [contaSelecionadaId, setContaSelecionadaId] = useState<number | null>(null);
  const [scoreRisco, setScoreRisco] = useState<ScoreRiscoConta | null>(null);
  const [interacoes, setInteracoes] = useState<InteracaoConta[]>([]);
  const [script, setScript] = useState<ScriptResgateConta | null>(null);
  const [modalInteracaoAberto, setModalInteracaoAberto] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [gerandoScript, setGerandoScript] = useState(false);

  async function carregarVisaoGeral() {
    const params = new URLSearchParams();
    if (filtroVendedorId) params.set("vendedor_usuario_id", String(filtroVendedorId));
    if (tenantSelecionadoId) params.set("tenant_id_selecionado", tenantSelecionadoId);
    const filtro = params.toString() ? `?${params.toString()}` : "";
    try {
      const [dashboardResp, rankingResp] = await Promise.all([
        api.get<DashboardSaudeContas>(`/saude-contas/dashboard${filtro}`),
        api.get<SaudeConta[]>(`/saude-contas/ranking${filtro}`),
      ]);
      setDashboard(dashboardResp);
      setRanking(rankingResp);
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível carregar o MAP.");
    }
  }

  async function carregarDetalheConta(contaId: number) {
    setScript(null);
    try {
      const [scoreResp, interacoesResp] = await Promise.all([
        api.get<ScoreRiscoConta>(`/saude-contas/contas/${contaId}/score-risco`),
        api.get<InteracaoConta[]>(`/saude-contas/contas/${contaId}/interacoes`),
      ]);
      setScoreRisco(scoreResp);
      setInteracoes(interacoesResp);
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível carregar o detalhe da conta.");
    }
  }

  useEffect(() => {
    carregarVisaoGeral();
  }, [filtroVendedorId, tenantSelecionadoId]);

  useEffect(() => {
    if (isGestor) {
      api
        .get<UsuarioResumo[]>("/usuarios")
        .then(setVendedores)
        .catch(() => undefined);
    }
  }, [isGestor]);

  useEffect(() => {
    if (podeVerHierarquia) {
      api
        .get<TenantResumo[]>("/admin/tenants")
        .then(setTenantsVisiveis)
        .catch(() => undefined);
    }
  }, [podeVerHierarquia]);

  useEffect(() => {
    // `GET /usuarios` só devolve os usuários do PRÓPRIO tenant do
    // chamador — ao trocar pra outro tenant da hierarquia, o filtro de
    // vendedor não teria como ser aplicado corretamente, então reseta
    // (raio-X 2026-09-10, escopo desta rodada não cobre filtrar vendedor
    // dentro de um tenant alheio ainda).
    setFiltroVendedorId(null);
  }, [tenantSelecionadoId]);

  useEffect(() => {
    if (contaSelecionadaId) carregarDetalheConta(contaSelecionadaId);
  }, [contaSelecionadaId]);

  async function registrarInteracao(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!contaSelecionadaId) return;
    const form = new FormData(event.currentTarget);
    try {
      await api.post("/saude-contas/interacoes", {
        conta_id: contaSelecionadaId,
        tipo: String(form.get("tipo")),
        descricao: String(form.get("descricao") || "") || null,
      });
      setModalInteracaoAberto(false);
      await Promise.all([carregarDetalheConta(contaSelecionadaId), carregarVisaoGeral()]);
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível registrar a interação.");
    }
  }

  async function gerarScript() {
    if (!contaSelecionadaId) return;
    setGerandoScript(true);
    try {
      setScript(await api.get<ScriptResgateConta>(`/saude-contas/contas/${contaSelecionadaId}/script-resgate`));
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível gerar o script de resgate.");
    } finally {
      setGerandoScript(false);
    }
  }

  const contaNome = ranking.find((item) => item.conta_id === contaSelecionadaId);
  const contaTitulo = contaNome ? contaNome.nome_fantasia || contaNome.nome : null;
  // Mostra a coluna "Empresa" só pra quem realmente gerencia mais de um
  // tenant — a maioria dos admins de tenant "cliente" não vê mudança
  // nenhuma nesta tela (raio-X 2026-09-10).
  const mostraColunaTenant = podeVerHierarquia && tenantsVisiveis.length > 1;

  const rankingFiltrado = useMemo(() => {
    const termo = busca.trim().toLowerCase();
    if (!termo) return ranking;
    return ranking.filter(
      (item) => item.nome.toLowerCase().includes(termo) || (item.nome_fantasia ?? "").toLowerCase().includes(termo),
    );
  }, [ranking, busca]);

  return (
    <div className="p-5.5">
      <div className="mb-5 flex items-end justify-between">
        <div>
          <div className="font-head text-xl font-bold">MAP — Motor de Alta Performance</div>
          <div className="mt-0.5 text-[11px] text-muted">
            {isGestor
              ? "Saúde das contas de todo o time — filtre por vendedor para focar numa carteira"
              : "Saúde das contas da sua carteira"}
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Input
            value={busca}
            onChange={(event) => setBusca(event.target.value)}
            placeholder="Buscar por empresa..."
            className="w-52"
          />
          {podeVerHierarquia && (
            <Select
              value={tenantSelecionadoId ?? ""}
              onChange={(event) => setTenantSelecionadoId(event.target.value || null)}
              className="w-56"
            >
              <option value="">Toda a hierarquia</option>
              {tenantsVisiveis.map((tenant) => (
                <option key={tenant.id} value={tenant.id}>
                  {tenant.razao_social}
                </option>
              ))}
            </Select>
          )}
          {isGestor && !tenantSelecionadoId && (
            <Select
              value={filtroVendedorId ?? ""}
              onChange={(event) => setFiltroVendedorId(event.target.value ? Number(event.target.value) : null)}
              className="w-56"
            >
              <option value="">Todos os vendedores</option>
              {vendedores.map((vendedor) => (
                <option key={vendedor.id} value={vendedor.id}>
                  {vendedor.nome}
                </option>
              ))}
            </Select>
          )}
        </div>
      </div>

      {erro && <div className="mb-4 text-[12px] text-red">{erro}</div>}

      <div className="mb-4 grid grid-cols-2 gap-2.5 sm:grid-cols-3">
        <KpiCard label="Score médio" value={dashboard?.score_medio?.toFixed(0) ?? "—"} colorClassName="text-cyan" />
        <KpiCard label="Críticas" value={dashboard?.criticas ?? "—"} colorClassName="text-red" />
        <KpiCard label="Atenção" value={dashboard?.atencao ?? "—"} colorClassName="text-amber" />
        <KpiCard
          label="Pipeline em risco"
          value={dashboard ? `R$${Math.round(dashboard.valor_total_em_risco / 1000)}k` : "—"}
          colorClassName="text-red"
        />
        <KpiCard
          label="ROI (LTV/CAC)"
          value={dashboard?.roi != null ? `${dashboard.roi.toFixed(1)}x` : "—"}
          colorClassName="text-violet"
        />
        <KpiCard
          label="CS Score"
          value={dashboard?.cs_score != null ? dashboard.cs_score.toFixed(0) : "—"}
          sub={dashboard?.nps_medio != null ? `NPS médio ${dashboard.nps_medio.toFixed(1)}` : undefined}
          colorClassName="text-green"
        />
      </div>

      <div className="grid grid-cols-1 gap-3.5 lg:grid-cols-2">
        <Card>
          <SectionLabel>Ranking de saúde das contas</SectionLabel>
          <table className="w-full border-collapse text-[12px]">
            <thead>
              <tr className="border-b border-border text-[9.5px] tracking-wide text-muted uppercase">
                <th className="p-2 text-left">Conta</th>
                {mostraColunaTenant && <th className="p-2 text-left">Empresa</th>}
                {isGestor && <th className="p-2 text-left">Vendedor</th>}
                <th className="p-2 text-left">Score</th>
                <th className="p-2 text-left">Pipeline aberto</th>
              </tr>
            </thead>
            <tbody>
              {rankingFiltrado.map((item) => (
                <tr
                  key={item.conta_id}
                  onClick={() => setContaSelecionadaId(item.conta_id)}
                  className={`cursor-pointer border-b border-border ${
                    item.conta_id === contaSelecionadaId ? "bg-surf2" : ""
                  }`}
                >
                  <td className="p-2 font-semibold">{item.nome_fantasia || item.nome}</td>
                  {mostraColunaTenant && <td className="p-2 text-muted">{item.tenant_nome}</td>}
                  {isGestor && <td className="p-2 text-muted">{item.vendedor_nome ?? "—"}</td>}
                  <td className="p-2">
                    <Badge tone={toneClassificacao(item.classificacao)}>{item.score.toFixed(0)}</Badge>
                  </td>
                  <td className="p-2 text-muted">R${Math.round(item.valor_pipeline_aberto / 1000)}k</td>
                </tr>
              ))}
              {rankingFiltrado.length === 0 && (
                <tr>
                  <td colSpan={isGestor ? (mostraColunaTenant ? 5 : 4) : 3} className="p-4 text-center text-muted">
                    {ranking.length > 0
                      ? "Nenhuma conta encontrada para essa busca."
                      : isGestor
                        ? "Nenhuma conta encontrada."
                        : "Nenhuma conta atribuída a você ainda — peça ao seu gestor para vincular contas ao seu nome."}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </Card>

        <Card glow>
          <SectionLabel>{contaTitulo ? `Detalhe — ${contaTitulo}` : "Selecione uma conta no ranking"}</SectionLabel>

          {contaSelecionadaId && scoreRisco && (
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

      <Modal title="Registrar interação" open={modalInteracaoAberto} onClose={() => setModalInteracaoAberto(false)}>
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
