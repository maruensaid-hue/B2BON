import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Navigate } from "react-router-dom";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, SectionLabel } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { KpiCard } from "@/components/ui/KpiCard";
import { AcessoRestrito } from "@/pages/admin/AcessoRestrito";
import { brl, type Pacote } from "@/lib/aiCredits";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";

/** AI FinOps — painel da plataforma (Fases 5 e 15, só super_admin).
 * Receita dos AI Credits × custo real de IA, margens por dimensão com
 * alertas por janela e amostra mínima, matriz de rentabilidade,
 * recomendações de peso (nunca aplicadas sozinhas), catálogos versionados
 * e ajustes auditados. O admin do tenant usa a página AI Credits. */

interface Kpis {
  ai_revenue_brl: number;
  ai_variable_cost_brl: number | null;
  ai_variable_cost_usd: number;
  ai_gross_profit_brl: number | null;
  ai_gross_margin: number | null;
  nivel_margem: string | null;
  margem_alvo: number;
  motivo_indisponivel: string | null;
  execucoes: number;
  credits_sold: number;
  credits_sold_revenue_brl: number;
  credits_consumed: number;
  credits_expired: number;
  unused_credit_liability: { creditos: number; valor_brl: number };
  overage: { creditos: number; receita_brl: number };
  avg_cost_per_1k_credits_brl: number | null;
  avg_revenue_per_1k_credits_brl: number | null;
  cache_savings_usd: number;
  cache_hit_rate: number | null;
}

interface LinhaMargem {
  chave: string | null;
  execucoes: number;
  creditos: number;
  receita_brl: number;
  custo_usd: number;
  custo_brl: number | null;
  margem_bruta: number | null;
  nivel: string | null;
  amostra_suficiente: boolean;
  modulo?: string;
  economicamente_inadequado?: boolean;
}

interface AlertaMargem {
  alerta: string;
  janela_dias: number;
  dimensao: string;
  chave: string;
  margem_bruta: number;
  execucoes: number;
}

interface Recomendacao {
  workload: string;
  mensagem: string | null;
  direcao: string;
  peso_atual: number;
  peso_sugerido_min: number;
  peso_sugerido_max: number;
}

interface Catalogo {
  ativo: string;
  versoes: {
    versao: string;
    status: string;
    motivo: string | null;
    vigente_desde: string | null;
  }[];
  workloads: {
    codigo: string;
    nome: string;
    modulo: string;
    classe: string;
    creditos_base: number;
    custo_max_usd: number | null;
  }[];
}

interface Reconciliacao {
  tenant_id: string;
  disponivel: number;
  reservado: number;
  consistente: boolean;
  diferenca: number;
}

const DIMENSOES = [
  "modulo",
  "workload",
  "tenant",
  "plano",
  "pacote",
  "agente",
  "provider",
  "modelo",
];
const pct = (valor: number | null) =>
  valor === null ? "—" : `${(valor * 100).toFixed(1)}%`;
const TOM_NIVEL: Record<string, "green" | "amber" | "red" | "muted"> = {
  OK: "green",
  ABAIXO_DO_ALVO: "amber",
  MARGIN_WARNING: "amber",
  MARGIN_CRITICAL: "red",
};

function useCarregar<T>(caminho: string) {
  const [dados, setDados] = useState<T | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const recarregar = useCallback(() => {
    api
      .get<T>(caminho)
      .then((r) => {
        setDados(r);
        setErro(null);
      })
      .catch((e) =>
        setErro(e instanceof ApiError ? e.message : "Falha ao carregar."),
      );
  }, [caminho]);
  useEffect(() => {
    recarregar();
  }, [recarregar]);
  return { dados, erro, recarregar };
}

function Nivel({ nivel }: { nivel: string | null }) {
  if (!nivel) return <span className="text-muted">—</span>;
  return <Badge tone={TOM_NIVEL[nivel] ?? "muted"}>{nivel}</Badge>;
}

function Resumo({ dias }: { dias: number }) {
  const { dados: k, erro } = useCarregar<Kpis>(`/finops/economia?dias=${dias}`);
  if (!k)
    return (
      <div className="mb-4 text-[12px] text-muted">{erro ?? "Carregando…"}</div>
    );
  return (
    <>
      <div className="mb-2 grid grid-cols-2 gap-2.5 sm:grid-cols-4">
        <KpiCard
          label="Receita de IA"
          value={brl(k.ai_revenue_brl)}
          sub={`${k.execucoes} execuções`}
          colorClassName="text-green"
        />
        <KpiCard
          label="Custo de IA"
          value={
            k.ai_variable_cost_brl === null
              ? `US$ ${k.ai_variable_cost_usd.toFixed(2)}`
              : brl(k.ai_variable_cost_brl)
          }
          colorClassName="text-red"
        />
        <KpiCard
          label="Lucro bruto"
          value={
            k.ai_gross_profit_brl === null ? "—" : brl(k.ai_gross_profit_brl)
          }
        />
        <KpiCard
          label="Margem bruta"
          value={pct(k.ai_gross_margin)}
          sub={`alvo ${pct(k.margem_alvo)}`}
          colorClassName="text-amber"
        />
      </div>
      {k.motivo_indisponivel && (
        <div className="mb-2 text-[11px] text-amber">
          {k.motivo_indisponivel}
        </div>
      )}
      <Card className="mb-4 text-[12px]">
        <div className="grid grid-cols-1 gap-1 sm:grid-cols-3">
          <div>
            Créditos vendidos: <b>{k.credits_sold.toLocaleString("pt-BR")}</b> (
            {brl(k.credits_sold_revenue_brl)})
          </div>
          <div>
            Créditos consumidos:{" "}
            <b>{k.credits_consumed.toLocaleString("pt-BR")}</b>
          </div>
          <div>
            Créditos expirados:{" "}
            <b>{k.credits_expired.toLocaleString("pt-BR")}</b>
          </div>
          <div>
            Passivo de créditos não usados:{" "}
            <b>{k.unused_credit_liability.creditos.toLocaleString("pt-BR")}</b>{" "}
            ({brl(k.unused_credit_liability.valor_brl)})
          </div>
          <div>
            Excedente faturável:{" "}
            <b>{k.overage.creditos.toLocaleString("pt-BR")}</b> (
            {brl(k.overage.receita_brl)})
          </div>
          <div>
            Receita / custo por 1.000 créditos:{" "}
            <b>
              {k.avg_revenue_per_1k_credits_brl === null
                ? "—"
                : brl(k.avg_revenue_per_1k_credits_brl)}
            </b>{" "}
            /{" "}
            <b>
              {k.avg_cost_per_1k_credits_brl === null
                ? "—"
                : brl(k.avg_cost_per_1k_credits_brl)}
            </b>
          </div>
          <div>
            Economia com cache: <b>US$ {k.cache_savings_usd.toFixed(4)}</b>
          </div>
          <div>
            Cache hit rate: <b>{pct(k.cache_hit_rate)}</b>
          </div>
        </div>
      </Card>
    </>
  );
}

function Margens({ dias }: { dias: number }) {
  const [dimensao, setDimensao] = useState("modulo");
  const { dados } = useCarregar<LinhaMargem[]>(
    `/finops/margens?dimensao=${dimensao}&dias=${dias}`,
  );
  return (
    <Card className="mb-4">
      <div className="mb-2 flex items-center justify-between">
        <SectionLabel>Margem por dimensão</SectionLabel>
        <select
          value={dimensao}
          onChange={(e) => setDimensao(e.target.value)}
          className="rounded-md border border-border bg-transparent px-2 py-1 text-[12px]"
        >
          {DIMENSOES.map((d) => (
            <option key={d} value={d}>
              {d}
            </option>
          ))}
        </select>
      </div>
      <table className="w-full border-collapse text-[12px]">
        <thead>
          <tr className="border-b border-border text-[9.5px] tracking-wide text-muted uppercase">
            <th className="p-2 text-left">Item</th>
            <th className="p-2 text-right">Execuções</th>
            <th className="p-2 text-right">Créditos</th>
            <th className="p-2 text-right">Receita</th>
            <th className="p-2 text-right">Custo</th>
            <th className="p-2 text-right">Margem</th>
            <th className="p-2 text-right">Situação</th>
          </tr>
        </thead>
        <tbody>
          {(dados ?? []).map((linha) => (
            <tr key={linha.chave ?? "—"} className="border-b border-border">
              <td className="p-2">{linha.chave ?? "—"}</td>
              <td className="p-2 text-right">{linha.execucoes}</td>
              <td className="p-2 text-right">
                {linha.creditos.toLocaleString("pt-BR")}
              </td>
              <td className="p-2 text-right">{brl(linha.receita_brl)}</td>
              <td className="p-2 text-right">
                {linha.custo_brl === null
                  ? `US$ ${linha.custo_usd.toFixed(4)}`
                  : brl(linha.custo_brl)}
              </td>
              <td className="p-2 text-right">{pct(linha.margem_bruta)}</td>
              <td className="p-2 text-right">
                <Nivel nivel={linha.nivel} />
                {!linha.amostra_suficiente && (
                  <span className="ml-1 text-[10px] text-muted">
                    amostra pequena
                  </span>
                )}
              </td>
            </tr>
          ))}
          {dados?.length === 0 && (
            <tr>
              <td colSpan={7} className="p-3 text-center text-muted">
                Sem execuções no período.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </Card>
  );
}

function AlertasERecomendacoes({ dias }: { dias: number }) {
  const alertas = useCarregar<AlertaMargem[]>("/finops/alertas-margem");
  const recomendacoes = useCarregar<Recomendacao[]>(
    `/finops/recomendacoes-peso?dias=${dias}`,
  );
  const matriz = useCarregar<LinhaMargem[]>(
    `/finops/matriz-rentabilidade?dias=${dias}`,
  );
  const inadequados = (matriz.dados ?? []).filter(
    (l) => l.economicamente_inadequado,
  );
  return (
    <div className="mb-4 grid grid-cols-1 gap-3.5 lg:grid-cols-3">
      <Card>
        <SectionLabel>Alertas de margem</SectionLabel>
        <div className="mb-1 text-[10.5px] text-muted">
          Janelas de 7 e 30 dias, só com amostra mínima.
        </div>
        {(alertas.dados ?? []).map((a) => (
          <div
            key={`${a.janela_dias}-${a.dimensao}-${a.chave}`}
            className="flex justify-between py-1 text-[12px]"
          >
            <span>
              {a.dimensao}: {a.chave} ({a.janela_dias}d)
            </span>
            <span>
              {pct(a.margem_bruta)} <Nivel nivel={a.alerta} />
            </span>
          </div>
        ))}
        {alertas.dados?.length === 0 && (
          <div className="text-[12px] text-muted">Nenhum alerta.</div>
        )}
      </Card>
      <Card>
        <SectionLabel>Workloads economicamente inadequados</SectionLabel>
        {inadequados.map((l) => (
          <div key={l.chave} className="flex justify-between py-1 text-[12px]">
            <span>
              {l.modulo} · {l.chave}
            </span>
            <span>{pct(l.margem_bruta)}</span>
          </div>
        ))}
        {inadequados.length === 0 && (
          <div className="text-[12px] text-muted">Nenhum no período.</div>
        )}
      </Card>
      <Card>
        <SectionLabel>Recomendações de peso</SectionLabel>
        <div className="mb-1 text-[10.5px] text-muted">
          Nunca aplicadas automaticamente: crie um rascunho do catálogo e
          aprove.
        </div>
        {(recomendacoes.dados ?? []).map((r) => (
          <div
            key={r.workload}
            className="border-b border-border py-1 text-[12px]"
          >
            <Badge tone={r.direcao === "AUMENTAR" ? "red" : "muted"}>
              {r.direcao}
            </Badge>{" "}
            {r.mensagem}
          </div>
        ))}
        {recomendacoes.dados?.length === 0 && (
          <div className="text-[12px] text-muted">Sem amostra suficiente.</div>
        )}
      </Card>
    </div>
  );
}

function CatalogoVersionado() {
  const { dados, recarregar } = useCarregar<Catalogo>("/finops/catalogo");
  const [mensagem, setMensagem] = useState<string | null>(null);

  async function criarRascunho(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    try {
      const r = await api.post<{ versao: string }>(
        "/finops/catalogo/rascunhos",
        {
          mudancas: {
            [String(form.get("workload"))]: {
              creditos_base: Number(form.get("creditos_base")),
            },
          },
          motivo: String(form.get("motivo")),
        },
      );
      setMensagem(`Rascunho ${r.versao} criado. Ative para valer.`);
      recarregar();
    } catch (error) {
      setMensagem(
        error instanceof ApiError ? error.message : "Falha ao criar rascunho.",
      );
    }
  }

  async function ativar(versao: string) {
    const motivo = window.prompt(`Motivo para ativar ${versao}:`);
    if (!motivo) return;
    try {
      await api.post(`/finops/catalogo/${versao}/ativar`, { motivo });
      setMensagem(`${versao} ativo.`);
      recarregar();
    } catch (error) {
      setMensagem(
        error instanceof ApiError ? error.message : "Falha ao ativar.",
      );
    }
  }

  if (!dados) return null;
  return (
    <Card className="mb-4">
      <SectionLabel>Catálogo de workloads (ativo: {dados.ativo})</SectionLabel>
      <div className="mb-2 flex flex-wrap gap-1.5 text-[11px]">
        {dados.versoes.map((v) => (
          <span
            key={v.versao}
            className="flex items-center gap-1 rounded border border-border px-2 py-0.5"
          >
            {v.versao}{" "}
            <Badge tone={v.status === "ATIVO" ? "green" : "muted"}>
              {v.status}
            </Badge>
            {v.status === "RASCUNHO" && (
              <button
                type="button"
                className="text-cyan"
                onClick={() => ativar(v.versao)}
              >
                ativar
              </button>
            )}
          </span>
        ))}
      </div>
      <form
        onSubmit={criarRascunho}
        className="flex flex-wrap gap-2 text-[12px]"
      >
        <select
          name="workload"
          className="rounded-md border border-border bg-transparent px-2 py-1.5"
        >
          {dados.workloads.map((w) => (
            <option key={w.codigo} value={w.codigo}>
              {w.codigo} ({w.creditos_base})
            </option>
          ))}
        </select>
        <Input
          name="creditos_base"
          type="number"
          min="0"
          step="0.5"
          required
          placeholder="Novo peso"
        />
        <Input
          name="motivo"
          required
          minLength={3}
          placeholder="Motivo (auditado)"
        />
        <Button size="sm" type="submit">
          Criar rascunho
        </Button>
      </form>
      {mensagem && (
        <div className="mt-1 text-[11px] text-muted">{mensagem}</div>
      )}
    </Card>
  );
}

function Pacotes() {
  const { dados, recarregar } =
    useCarregar<(Pacote & { valido_ate: string | null })[]>("/finops/pacotes");
  const [mensagem, setMensagem] = useState<string | null>(null);

  async function novaVersao(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    try {
      await api.post(`/finops/pacotes/${String(form.get("codigo"))}/versoes`, {
        preco: Number(form.get("preco")),
        creditos: Number(form.get("creditos")),
        validade_meses: 12,
        motivo: String(form.get("motivo")),
      });
      setMensagem(
        "Nova versão publicada. Compras anteriores mantêm a versão paga.",
      );
      recarregar();
    } catch (error) {
      setMensagem(
        error instanceof ApiError ? error.message : "Falha ao criar versão.",
      );
    }
  }

  if (!dados) return null;
  return (
    <Card className="mb-4">
      <SectionLabel>Pacotes (versões)</SectionLabel>
      {dados.map((p) => (
        <div
          key={`${p.codigo}-${p.versao}`}
          className="flex justify-between border-b border-border py-1 text-[12px]"
        >
          <span>
            {p.nome} v{p.versao}{" "}
            {p.valido_ate ? (
              <span className="text-muted">(encerrada)</span>
            ) : null}
          </span>
          <span className="text-muted">
            {p.creditos?.toLocaleString("pt-BR") ?? "—"} ·{" "}
            {p.preco === null ? p.status : brl(p.preco)}
          </span>
        </div>
      ))}
      <div className="mt-2 text-[10.5px] text-muted">
        Mudança de preço só com decisão do PO: cria nova versão auditada.
      </div>
      <form
        onSubmit={novaVersao}
        className="mt-1 flex flex-wrap gap-2 text-[12px]"
      >
        <Input name="codigo" required placeholder="Código (ex.: AI_START)" />
        <Input
          name="creditos"
          type="number"
          min="1"
          required
          placeholder="Créditos"
        />
        <Input
          name="preco"
          type="number"
          min="0.01"
          step="0.01"
          required
          placeholder="Preço (R$)"
        />
        <Input
          name="motivo"
          required
          minLength={3}
          placeholder="Motivo / aprovação"
        />
        <Button size="sm" type="submit">
          Nova versão
        </Button>
      </form>
      {mensagem && (
        <div className="mt-1 text-[11px] text-muted">{mensagem}</div>
      )}
    </Card>
  );
}

function AjustesEConciliacao() {
  const { dados, recarregar } = useCarregar<Reconciliacao[]>(
    "/finops/reconciliacao",
  );
  const [mensagem, setMensagem] = useState<string | null>(null);

  async function ajustar(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formulario = event.currentTarget;
    const form = new FormData(formulario);
    try {
      await api.post(
        `/finops/tenants/${String(form.get("tenant_id"))}/creditos`,
        {
          quantidade: Number(form.get("quantidade")),
          tipo: String(form.get("tipo")),
          motivo: String(form.get("motivo")),
          validade_dias: form.get("validade_dias")
            ? Number(form.get("validade_dias"))
            : null,
        },
      );
      formulario.reset();
      setMensagem("Ajuste registrado e auditado.");
      recarregar();
    } catch (error) {
      setMensagem(
        error instanceof ApiError ? error.message : "Falha no ajuste.",
      );
    }
  }

  async function excedente(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const numero = (campo: string) =>
      form.get(campo) ? Number(form.get(campo)) : null;
    try {
      await api.put(
        `/finops/tenants/${String(form.get("tenant_id"))}/excedente`,
        {
          ativo: form.get("ativo") === "on",
          orcamento_mensal: numero("orcamento_mensal"),
          limite_suave: numero("limite_suave"),
          limite_rigido: numero("limite_rigido"),
          franquia_personalizada: numero("franquia_personalizada"),
          motivo: String(form.get("motivo")),
        },
      );
      setMensagem("Contrato Enterprise atualizado.");
    } catch (error) {
      setMensagem(
        error instanceof ApiError
          ? error.message
          : "Falha ao salvar excedente.",
      );
    }
  }

  return (
    <div className="grid grid-cols-1 gap-3.5 lg:grid-cols-2">
      <Card>
        <SectionLabel>Ajuste / promoção de créditos</SectionLabel>
        <form onSubmit={ajustar} className="flex flex-wrap gap-2 text-[12px]">
          <Input name="tenant_id" required placeholder="tenant_id" />
          <Input
            name="quantidade"
            type="number"
            step="1"
            required
            placeholder="Quantidade (negativo debita)"
          />
          <select
            name="tipo"
            className="rounded-md border border-border bg-transparent px-2 py-1.5"
          >
            <option value="ADJUSTMENT">Ajuste</option>
            <option value="PROMOTIONAL">Promocional</option>
          </select>
          <Input
            name="validade_dias"
            type="number"
            min="1"
            placeholder="Validade (dias)"
          />
          <Input
            name="motivo"
            required
            minLength={3}
            placeholder="Motivo (auditado)"
          />
          <Button size="sm" type="submit">
            Registrar
          </Button>
        </form>
        <SectionLabel className="mt-4">
          Enterprise: pool e excedente pós-pago
        </SectionLabel>
        <form onSubmit={excedente} className="flex flex-wrap gap-2 text-[12px]">
          <Input name="tenant_id" required placeholder="tenant_id" />
          <Input
            name="franquia_personalizada"
            type="number"
            min="0"
            placeholder="Pool mensal"
          />
          <Input
            name="orcamento_mensal"
            type="number"
            min="1"
            placeholder="Orçamento de excedente"
          />
          <Input
            name="limite_suave"
            type="number"
            min="1"
            placeholder="Limite suave"
          />
          <Input
            name="limite_rigido"
            type="number"
            min="1"
            placeholder="Limite rígido"
          />
          <label className="flex items-center gap-1">
            <input type="checkbox" name="ativo" /> excedente ativo
          </label>
          <Input
            name="motivo"
            required
            minLength={3}
            placeholder="Contrato / motivo"
          />
          <Button size="sm" type="submit">
            Salvar
          </Button>
        </form>
        {mensagem && (
          <div className="mt-1 text-[11px] text-muted">{mensagem}</div>
        )}
      </Card>
      <Card>
        <SectionLabel>Reconciliação (extrato × lotes × reservas)</SectionLabel>
        {(dados ?? []).map((r) => (
          <div
            key={r.tenant_id}
            className="flex justify-between border-b border-border py-1 text-[12px]"
          >
            <span>{r.tenant_id}</span>
            <span>
              {r.disponivel.toLocaleString("pt-BR")} disp.{" "}
              {r.consistente ? (
                <Badge tone="green">OK</Badge>
              ) : (
                <Badge tone="red">Diferença {r.diferenca}</Badge>
              )}
            </span>
          </div>
        ))}
        {dados?.length === 0 && (
          <div className="text-[12px] text-muted">Sem carteiras.</div>
        )}
      </Card>
    </div>
  );
}

export function FinOpsIa() {
  const { usuario } = useAuth();
  const [dias, setDias] = useState(30);
  if (usuario?.papel === "admin") return <Navigate to="/ai-credits" replace />;
  if (usuario?.papel !== "super_admin") return <AcessoRestrito />;
  return (
    <div className="p-5.5">
      <div className="mb-5 flex flex-wrap items-end justify-between gap-2">
        <div>
          <div className="font-head text-xl font-bold">AI FinOps</div>
          <div className="mt-0.5 text-[11px] text-muted">
            Receita dos AI Credits, custo real de IA e margens. Nada aqui muda
            preço ou peso sem aprovação.
          </div>
        </div>
        <select
          value={dias}
          onChange={(e) => setDias(Number(e.target.value))}
          className="rounded-md border border-border bg-transparent px-2 py-1 text-[12px]"
        >
          <option value={7}>7 dias</option>
          <option value={30}>30 dias</option>
          <option value={90}>90 dias</option>
        </select>
      </div>
      <Resumo dias={dias} />
      <AlertasERecomendacoes dias={dias} />
      <Margens dias={dias} />
      <CatalogoVersionado />
      <Pacotes />
      <AjustesEConciliacao />
    </div>
  );
}
