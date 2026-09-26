import { useEffect, useMemo, useState } from "react";

import { PainelDesempenho } from "@/components/dashboard/PainelDesempenho";
import { Badge } from "@/components/ui/Badge";
import { Card, SectionLabel } from "@/components/ui/Card";
import { Input, Select } from "@/components/ui/Input";
import { KpiCard } from "@/components/ui/KpiCard";
import { TutorialMap } from "@/pages/map/TutorialMap";
import { DetalheRisco } from "@/pages/map/DetalheRisco";
import { toneClassificacao } from "@/pages/map/risco";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";

interface ContaResumoVendedor {
  id: number;
  nome: string;
  nome_fantasia: string | null;
  score: number;
  classificacao: string;
}

interface VendedorComContas {
  usuario_id: number;
  nome: string;
  contas: ContaResumoVendedor[];
}

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

interface UsuarioResumo {
  id: number;
  nome: string;
}

interface TenantResumo {
  id: string;
  razao_social: string;
}

/** Visão de user/admin — saúde das CONTAS (clientes/prospects) dentro do
 * próprio tenant. Vendedor (user) só vê a carteira dele; gestor (admin)
 * vê o time inteiro e pode filtrar por vendedor. Distinta de
 * MapTenants.tsx, exclusiva do super_admin. */
export function MapContas() {
  const { usuario, marcarTutorialModuloVisto } = useAuth();
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
  const [erro, setErro] = useState<string | null>(null);
  // Árvore vendedor → contas (raio-X 2026-09-24, MAP espelha o
  // Dashboard) — só pra quem já vê múltiplos vendedores, e só dentro
  // do próprio tenant (sem cross-tenant, escopo desta rodada).
  const [vendedoresComContas, setVendedoresComContas] = useState<VendedorComContas[]>([]);
  const [vendedoresExpandidosIds, setVendedoresExpandidosIds] = useState<Set<number>>(new Set());
  const [vendedorDesempenhoId, setVendedorDesempenhoId] = useState<number | null>(null);
  // Tutorial do módulo (raio-X 2026-09-21) — abre sozinho na primeira
  // visita, coexiste com o tour grande. `carregado` evita a corrida com
  // o `carregarVisaoGeral()` async (mesmo padrão de Kanban.tsx).
  const [tutorialAberto, setTutorialAberto] = useState(false);
  const [carregado, setCarregado] = useState(false);
  useEffect(() => {
    if (usuario && carregado && !(usuario.tutoriais_modulo_vistos ?? []).includes("map")) setTutorialAberto(true);
  }, [usuario, carregado]);
  function fecharTutorial() {
    setTutorialAberto(false);
    if (usuario && !(usuario.tutoriais_modulo_vistos ?? []).includes("map")) marcarTutorialModuloVisto("map");
  }

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
    } finally {
      setCarregado(true);
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
    if (isGestor && !tenantSelecionadoId) {
      api
        .get<VendedorComContas[]>("/saude-contas/vendedores-com-contas")
        .then(setVendedoresComContas)
        .catch(() => setVendedoresComContas([]));
    } else {
      setVendedoresComContas([]);
    }
  }, [isGestor, tenantSelecionadoId]);

  function alternarVendedorExpandido(usuarioId: number) {
    setVendedoresExpandidosIds((atual) => {
      const novo = new Set(atual);
      if (novo.has(usuarioId)) novo.delete(usuarioId);
      else novo.add(usuarioId);
      return novo;
    });
  }

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
          <div className="flex items-center gap-2">
            <div className="font-head text-xl font-bold">MAP — Motor de Alta Performance</div>
            <button type="button" onClick={() => setTutorialAberto(true)} className="text-[11px] text-muted hover:text-cyan">
              🔄 Rever tutorial
            </button>
          </div>
          <div className="mt-0.5 text-[11px] text-muted">
            {isGestor
              ? "Saúde das contas de todo o time — filtre por vendedor para focar numa carteira"
              : "Saúde das contas da sua carteira"}
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Input
            data-tutorial-id="map:busca"
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

      <div data-tutorial-id="map:kpis" className="mb-4 grid grid-cols-2 gap-2.5 sm:grid-cols-3">
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

      {vendedoresComContas.length > 0 && (
        <Card className="mb-4">
          <SectionLabel>Desempenho por vendedor</SectionLabel>
          <div className="flex flex-col gap-1">
            {vendedoresComContas.map((vendedor) => {
              const expandido = vendedoresExpandidosIds.has(vendedor.usuario_id);
              return (
                <div key={vendedor.usuario_id}>
                  <div className="flex items-center gap-2 py-1 text-[12px]">
                    <button
                      type="button"
                      className="text-muted hover:text-cyan"
                      onClick={() => alternarVendedorExpandido(vendedor.usuario_id)}
                    >
                      {expandido ? "▾" : "▸"}
                    </button>
                    <button
                      type="button"
                      className="font-semibold text-text hover:text-cyan hover:underline"
                      onClick={() => setVendedorDesempenhoId(vendedor.usuario_id)}
                    >
                      {vendedor.nome}
                    </button>
                    <span className="text-muted">
                      {vendedor.contas.length} conta{vendedor.contas.length === 1 ? "" : "s"}
                    </span>
                  </div>
                  {expandido && (
                    <div className="ml-6 flex flex-col gap-0.5 border-l border-border pl-3">
                      {vendedor.contas.map((conta) => (
                        <button
                          key={conta.id}
                          type="button"
                          onClick={() => setContaSelecionadaId(conta.id)}
                          className={`flex items-center justify-between gap-2 rounded-md px-2 py-1 text-left text-[11.5px] hover:bg-surf2 ${
                            conta.id === contaSelecionadaId ? "bg-surf2" : ""
                          }`}
                        >
                          <span>{conta.nome_fantasia || conta.nome}</span>
                          <Badge tone={toneClassificacao(conta.classificacao)}>{conta.score.toFixed(0)}</Badge>
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </Card>
      )}

      <div className="grid grid-cols-1 gap-3.5 lg:grid-cols-2">
        <Card data-tutorial-id="map:ranking">
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

          {contaSelecionadaId && (
            <DetalheRisco
              key={contaSelecionadaId}
              base={`/saude-contas/contas/${contaSelecionadaId}`}
              interacao={{ caminho: "/saude-contas/interacoes", alvo: { conta_id: contaSelecionadaId } }}
              aoRegistrar={carregarVisaoGeral}
              aoErro={setErro}
            />
          )}
        </Card>
      </div>


      {vendedorDesempenhoId !== null && (
        <div className="fixed inset-0 z-[70] flex items-start justify-center pt-[8vh]">
          <div className="absolute inset-0 bg-slate-950/70" onClick={() => setVendedorDesempenhoId(null)} />
          <div className="relative flex max-h-[84vh] w-full max-w-3xl flex-col overflow-hidden rounded-xl border border-border2 bg-surf shadow-2xl">
            <div className="flex items-center justify-between border-b border-border p-3">
              <div className="text-[13px] font-bold text-text">
                Desempenho — {vendedoresComContas.find((v) => v.usuario_id === vendedorDesempenhoId)?.nome}
              </div>
              <button type="button" className="text-muted hover:text-text" onClick={() => setVendedorDesempenhoId(null)}>
                ✕
              </button>
            </div>
            <div className="flex-1 overflow-y-auto p-4">
              <PainelDesempenho vendedorUsuarioId={vendedorDesempenhoId} origem="map" />
            </div>
          </div>
        </div>
      )}

      <TutorialMap open={tutorialAberto} onClose={fecharTutorial} />
    </div>
  );
}
