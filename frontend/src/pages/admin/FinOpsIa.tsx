import { useEffect, useState, type FormEvent } from "react";

import { Button } from "@/components/ui/Button";
import { Card, SectionLabel } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { KpiCard } from "@/components/ui/KpiCard";
import { AcessoRestrito } from "@/pages/admin/AcessoRestrito";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";

/** AI FinOps & Credits (Fase 5 do Master Prompt v4).
 * super_admin: custo real da plataforma (USD), política de créditos e alocação.
 * admin do tenant: consumo próprio em chamadas/créditos, saldo, orçamentos. */

interface Agrupado {
  chave: string | null;
  chamadas: number;
  custo_usd: number;
  tokens_entrada: number;
  tokens_saida: number;
  creditos: number;
}

interface ResumoPlataforma {
  politica_creditos: string | null;
  totais: {
    chamadas: number;
    custo_usd: number;
    chamadas_sem_preco: number;
    cache_ratio: number | null;
    creditos_consumidos: number;
    tokens_entrada: number;
    tokens_saida: number;
  };
  unitarios: Record<string, number | null>;
  indisponivel: Record<string, string | null>;
  por_tenant: Agrupado[];
  por_modulo: Agrupado[];
  por_feature: Agrupado[];
  por_modelo: Agrupado[];
}

interface MeuUso {
  politica_creditos: string | null;
  chamadas: number;
  creditos_consumidos: number;
  saldo_creditos: number;
  por_feature: { feature: string; chamadas: number; creditos: number }[];
}

interface Orcamento {
  orcamento_id: number;
  escopo: string;
  alvo: string | null;
  acao: string;
  chamadas: number;
  limite_chamadas: number | null;
  percentual: number | null;
  estourado: boolean;
  em_alerta: boolean;
}

const usd = (valor: number) => `US$ ${valor.toFixed(4)}`;
const ROTULO_POLITICA: Record<string, string> = {
  PENDING_DEFINITION: "Conversão em créditos a definir (custo já medido)",
  ATIVA: "Ativa",
};

function TabelaAgrupada({ titulo, linhas }: { titulo: string; linhas: Agrupado[] }) {
  return (
    <Card className="mb-4">
      <SectionLabel>{titulo}</SectionLabel>
      <table className="w-full border-collapse text-[12px]">
        <thead>
          <tr className="border-b border-border text-[9.5px] tracking-wide text-muted uppercase">
            <th className="p-2 text-left">Item</th>
            <th className="p-2 text-right">Chamadas</th>
            <th className="p-2 text-right">Tokens (entrada/saída)</th>
            <th className="p-2 text-right">Custo</th>
            <th className="p-2 text-right">Créditos</th>
          </tr>
        </thead>
        <tbody>
          {linhas.map((linha) => (
            <tr key={linha.chave ?? "—"} className="border-b border-border">
              <td className="p-2">{linha.chave ?? "—"}</td>
              <td className="p-2 text-right">{linha.chamadas}</td>
              <td className="p-2 text-right text-muted">
                {linha.tokens_entrada.toLocaleString("pt-BR")} / {linha.tokens_saida.toLocaleString("pt-BR")}
              </td>
              <td className="p-2 text-right">{usd(linha.custo_usd)}</td>
              <td className="p-2 text-right">{linha.creditos.toFixed(2)}</td>
            </tr>
          ))}
          {linhas.length === 0 && (
            <tr>
              <td colSpan={5} className="p-3 text-center text-muted">
                Sem uso no período.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </Card>
  );
}

function VisaoPlataforma() {
  const [resumo, setResumo] = useState<ResumoPlataforma | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  async function carregar() {
    try {
      setResumo(await api.get<ResumoPlataforma>("/finops/resumo"));
    } catch {
      setErro("Não foi possível carregar o FinOps.");
    }
  }

  useEffect(() => {
    carregar();
  }, []);

  async function definirPolitica(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    try {
      await api.post("/finops/politica-creditos", {
        creditos_por_usd: Number(form.get("creditos_por_usd")),
        permite_excedente: form.get("permite_excedente") === "on",
        exige_saldo: form.get("exige_saldo") === "on",
      });
      await carregar();
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível definir a política.");
    }
  }

  async function alocar(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formulario = event.currentTarget;
    const form = new FormData(formulario);
    try {
      await api.post(`/finops/tenants/${String(form.get("tenant_id"))}/creditos`, {
        quantidade: Number(form.get("quantidade")),
        descricao: String(form.get("descricao") || "") || null,
      });
      formulario.reset();
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível alocar créditos.");
    }
  }

  if (!resumo) return <div className="text-[12px] text-muted">{erro ?? "Carregando…"}</div>;
  const { totais } = resumo;

  return (
    <>
      {erro && <div className="mb-4 text-[12px] text-red">{erro}</div>}
      <div className="mb-4 grid grid-cols-2 gap-2.5 sm:grid-cols-4">
        <KpiCard label="Custo de IA (mês)" value={usd(totais.custo_usd)} sub="custo do provedor" colorClassName="text-red" />
        <KpiCard label="Chamadas" value={totais.chamadas} sub={`${totais.chamadas_sem_preco} sem preço cadastrado`} />
        <KpiCard
          label="Cache ratio"
          value={totais.cache_ratio === null ? "—" : `${(totais.cache_ratio * 100).toFixed(1)}%`}
          colorClassName="text-green"
        />
        <KpiCard label="Créditos consumidos" value={totais.creditos_consumidos.toFixed(2)} colorClassName="text-amber" />
      </div>

      <Card className="mb-4 text-[12px]">
        <SectionLabel>Unitários</SectionLabel>
        <div className="grid grid-cols-1 gap-1 sm:grid-cols-2">
          {Object.entries(resumo.unitarios).map(([chave, valor]) => (
            <div key={chave}>
              <span className="text-muted">{chave.replaceAll("_", " ")}: </span>
              {valor === null ? <span className="text-muted">{resumo.indisponivel[chave] ?? "sem dados no período"}</span> : usd(valor)}
            </div>
          ))}
          <div>
            <span className="text-muted">receita / margem de IA: </span>
            <span className="text-muted">{resumo.indisponivel.receita_ia}</span>
          </div>
        </div>
      </Card>

      <TabelaAgrupada titulo="Por tenant" linhas={resumo.por_tenant} />
      <TabelaAgrupada titulo="Por módulo" linhas={resumo.por_modulo} />
      <TabelaAgrupada titulo="Por feature" linhas={resumo.por_feature} />
      <TabelaAgrupada titulo="Por modelo" linhas={resumo.por_modelo} />

      <Card className="mb-4">
        <SectionLabel>Política de créditos</SectionLabel>
        <div className="mb-2 text-[12px]">
          Situação: <b>{ROTULO_POLITICA[resumo.politica_creditos ?? ""] ?? resumo.politica_creditos ?? "—"}</b>
        </div>
        <div className="mb-2 text-[11px] text-muted">
          A conversão custo → créditos é decisão comercial. Nunca é exibida ao cliente como “tokens por crédito”.
        </div>
        <form onSubmit={definirPolitica} className="flex flex-wrap items-center gap-2 text-[12px]">
          <Input name="creditos_por_usd" type="number" step="0.01" min="0.01" required placeholder="Créditos por US$ de custo" />
          <label className="flex items-center gap-1">
            <input type="checkbox" name="exige_saldo" /> exige saldo
          </label>
          <label className="flex items-center gap-1">
            <input type="checkbox" name="permite_excedente" /> permite excedente
          </label>
          <Button type="submit">Definir</Button>
        </form>
      </Card>

      <Card>
        <SectionLabel>Alocar créditos a um tenant</SectionLabel>
        <form onSubmit={alocar} className="flex flex-wrap gap-2">
          <Input name="tenant_id" required placeholder="tenant_id" />
          <Input name="quantidade" type="number" step="0.01" min="0.01" required placeholder="Quantidade" />
          <Input name="descricao" placeholder="Descrição" />
          <Button type="submit">Alocar</Button>
        </form>
      </Card>
    </>
  );
}

function VisaoTenant() {
  const [uso, setUso] = useState<MeuUso | null>(null);
  const [orcamentosAtivos, setOrcamentos] = useState<Orcamento[]>([]);
  const [erro, setErro] = useState<string | null>(null);

  async function carregar() {
    try {
      const [usoResp, orcamentosResp] = await Promise.all([
        api.get<MeuUso>("/finops/meu-uso"),
        api.get<Orcamento[]>("/finops/orcamentos"),
      ]);
      setUso(usoResp);
      setOrcamentos(orcamentosResp);
    } catch {
      setErro("Não foi possível carregar o consumo de IA.");
    }
  }

  useEffect(() => {
    carregar();
  }, []);

  async function criarOrcamento(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    try {
      await api.post("/finops/orcamentos", {
        limite_chamadas: Number(form.get("limite_chamadas")),
        acao: String(form.get("acao")),
      });
      await carregar();
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível criar o limite.");
    }
  }

  if (!uso) return <div className="text-[12px] text-muted">{erro ?? "Carregando…"}</div>;

  return (
    <>
      {erro && <div className="mb-4 text-[12px] text-red">{erro}</div>}
      <div className="mb-4 grid grid-cols-2 gap-2.5 sm:grid-cols-3">
        <KpiCard label="Chamadas de IA no mês" value={uso.chamadas} />
        <KpiCard label="Créditos consumidos" value={uso.creditos_consumidos.toFixed(2)} colorClassName="text-amber" />
        <KpiCard
          label="Saldo de créditos"
          value={uso.politica_creditos === "ATIVA" ? uso.saldo_creditos.toFixed(2) : "—"}
          sub={uso.politica_creditos === "ATIVA" ? undefined : "Créditos de IA em breve"}
          colorClassName="text-green"
        />
      </div>

      <Card className="mb-4">
        <SectionLabel>Uso por recurso</SectionLabel>
        {uso.por_feature.map((item) => (
          <div key={item.feature} className="flex justify-between border-b border-border py-1.5 text-[12px]">
            <span>{item.feature}</span>
            <span className="text-muted">
              {item.chamadas} chamadas · {item.creditos.toFixed(2)} créditos
            </span>
          </div>
        ))}
        {uso.por_feature.length === 0 && <div className="text-[12px] text-muted">Sem uso no mês.</div>}
      </Card>

      <Card>
        <SectionLabel>Limites mensais de IA</SectionLabel>
        {orcamentosAtivos.map((orcamento) => (
          <div key={orcamento.orcamento_id} className="border-b border-border py-1.5 text-[12px]">
            {orcamento.escopo}
            {orcamento.alvo ? `: ${orcamento.alvo}` : ""} — {orcamento.chamadas}/{orcamento.limite_chamadas ?? "∞"} chamadas (
            {orcamento.acao === "BLOQUEAR" ? "bloqueia" : "só alerta"})
            {orcamento.estourado && <span className="ml-2 text-red">limite atingido</span>}
            {!orcamento.estourado && orcamento.em_alerta && <span className="ml-2 text-amber">perto do limite</span>}
          </div>
        ))}
        <form onSubmit={criarOrcamento} className="mt-2 flex flex-wrap gap-2 text-[12px]">
          <Input name="limite_chamadas" type="number" min="1" required placeholder="Máximo de chamadas por mês" />
          <select name="acao" className="rounded-md border border-border bg-transparent px-2 py-1.5">
            <option value="ALERTAR">Só alertar</option>
            <option value="BLOQUEAR">Bloquear ao atingir</option>
          </select>
          <Button type="submit">Criar limite</Button>
        </form>
      </Card>
    </>
  );
}

export function FinOpsIa() {
  const { usuario } = useAuth();
  if (usuario?.papel !== "admin" && usuario?.papel !== "super_admin") return <AcessoRestrito />;
  return (
    <div className="p-5.5">
      <div className="mb-5">
        <div className="font-head text-xl font-bold">IA &amp; Créditos</div>
        <div className="mt-0.5 text-[11px] text-muted">
          {usuario.papel === "super_admin"
            ? "Custo real de IA da plataforma, por tenant, módulo, feature e modelo."
            : "Consumo de IA da sua empresa e limites mensais."}
        </div>
      </div>
      {usuario.papel === "super_admin" ? <VisaoPlataforma /> : <VisaoTenant />}
    </div>
  );
}
