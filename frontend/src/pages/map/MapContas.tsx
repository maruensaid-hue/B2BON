import { useEffect, useState, type FormEvent } from "react";

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
}

interface SaudeConta {
  conta_id: number;
  nome: string;
  nome_fantasia: string | null;
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

  const [dashboard, setDashboard] = useState<DashboardSaudeContas | null>(null);
  const [ranking, setRanking] = useState<SaudeConta[]>([]);
  const [vendedores, setVendedores] = useState<UsuarioResumo[]>([]);
  const [filtroVendedorId, setFiltroVendedorId] = useState<number | null>(null);
  const [contaSelecionadaId, setContaSelecionadaId] = useState<number | null>(null);
  const [scoreRisco, setScoreRisco] = useState<ScoreRiscoConta | null>(null);
  const [interacoes, setInteracoes] = useState<InteracaoConta[]>([]);
  const [script, setScript] = useState<ScriptResgateConta | null>(null);
  const [modalInteracaoAberto, setModalInteracaoAberto] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [gerandoScript, setGerandoScript] = useState(false);

  async function carregarVisaoGeral() {
    const filtro = filtroVendedorId ? `?vendedor_usuario_id=${filtroVendedorId}` : "";
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
  }, [filtroVendedorId]);

  useEffect(() => {
    if (isGestor) {
      api
        .get<UsuarioResumo[]>("/usuarios")
        .then(setVendedores)
        .catch(() => undefined);
    }
  }, [isGestor]);

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
        {isGestor && (
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

      {erro && <div className="mb-4 text-[12px] text-red">{erro}</div>}

      <div className="mb-4 grid grid-cols-2 gap-2.5 sm:grid-cols-4">
        <KpiCard label="Score médio" value={dashboard?.score_medio?.toFixed(0) ?? "—"} colorClassName="text-cyan" />
        <KpiCard label="Críticas" value={dashboard?.criticas ?? "—"} colorClassName="text-red" />
        <KpiCard label="Atenção" value={dashboard?.atencao ?? "—"} colorClassName="text-amber" />
        <KpiCard
          label="Pipeline em risco"
          value={dashboard ? `R$${Math.round(dashboard.valor_total_em_risco / 1000)}k` : "—"}
          colorClassName="text-red"
        />
      </div>

      <div className="grid grid-cols-1 gap-3.5 lg:grid-cols-2">
        <Card>
          <SectionLabel>Ranking de saúde das contas</SectionLabel>
          <table className="w-full border-collapse text-[12px]">
            <thead>
              <tr className="border-b border-border text-[9.5px] tracking-wide text-muted uppercase">
                <th className="p-2 text-left">Conta</th>
                {isGestor && <th className="p-2 text-left">Vendedor</th>}
                <th className="p-2 text-left">Score</th>
                <th className="p-2 text-left">Pipeline aberto</th>
              </tr>
            </thead>
            <tbody>
              {ranking.map((item) => (
                <tr
                  key={item.conta_id}
                  onClick={() => setContaSelecionadaId(item.conta_id)}
                  className={`cursor-pointer border-b border-border ${
                    item.conta_id === contaSelecionadaId ? "bg-surf2" : ""
                  }`}
                >
                  <td className="p-2 font-semibold">{item.nome_fantasia || item.nome}</td>
                  {isGestor && <td className="p-2 text-muted">{item.vendedor_nome ?? "—"}</td>}
                  <td className="p-2">
                    <Badge tone={toneClassificacao(item.classificacao)}>{item.score.toFixed(0)}</Badge>
                  </td>
                  <td className="p-2 text-muted">R${Math.round(item.valor_pipeline_aberto / 1000)}k</td>
                </tr>
              ))}
              {ranking.length === 0 && (
                <tr>
                  <td colSpan={isGestor ? 4 : 3} className="p-4 text-center text-muted">
                    {isGestor
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
