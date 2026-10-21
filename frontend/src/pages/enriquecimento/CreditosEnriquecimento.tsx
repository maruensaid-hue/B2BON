import { useEffect, useState, type FormEvent } from "react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, SectionLabel } from "@/components/ui/Card";
import { Input, Select } from "@/components/ui/Input";
import { KpiCard } from "@/components/ui/KpiCard";
import { api, mensagemErro } from "@/lib/api";
import { useAuth } from "@/lib/auth";

interface Painel {
  periodo: string;
  plano: {
    disponivel: boolean;
    origem?: string;
    versao?: number;
    faltando?: string[];
    franquia_creditos?: number | null;
    periodicidade?: string | null;
    decisores_por_empresa_padrao?: number | null;
    decisores_por_empresa_max?: number | null;
    itens_por_lote_max?: number | null;
    limite_periodo_creditos?: number | null;
    orientacao?: string | null;
  };
  creditos: { disponivel: number; reservado: number; saldo: number; consumido_no_periodo: number; expirado_no_periodo: number; concedido_no_periodo: number };
  pesquisas_por_estado: Record<string, number>;
  estimado_vs_reconciliado: { estimado_maximo: number; consumido: number };
  alertas: { codigo: string; mensagem: string }[];
}

interface Movimento {
  id: number;
  tipo: string;
  delta_saldo: number;
  delta_reservado: number;
  disponivel_apos: number;
  pesquisa_id: string | null;
  origem: string | null;
  motivo: string | null;
  criado_em: string;
}

interface PesquisaResumo {
  id: string;
  estado: string;
  total_empresas: number;
  decisores_por_empresa: number;
  total_maximo: number;
  creditos_consumidos: number;
  requer_reconciliacao: boolean;
  criado_em: string;
}

interface VisaoAdmin {
  orcamento_global: { provedor: string; nivel: string; limite: number | null; consumido: number; reservado: number; restante: number | null; percentual: number | null };
  pendentes_reconciliacao: { pesquisa_id: string; tenant_id: string; estado: string; empresas_ambiguas: number; creditos_reservados: number }[];
}

const TIPOS = ["", "CONCESSAO", "RENOVACAO", "RESERVA", "CONSUMO", "LIBERACAO", "ESTORNO", "EXPIRACAO", "AJUSTE", "RECONCILIACAO"];

const NIVEL_TOM: Record<string, "green" | "amber" | "red" | "muted"> = { ok: "green", alerta: "amber", esgotado: "red", nao_configurado: "red" };
const NIVEL_ROTULO: Record<string, string> = {
  ok: "Dentro do limite", alerta: "Perto do limite", esgotado: "Esgotado", nao_configurado: "Não configurado — chamadas ao provedor bloqueadas",
};

function dataCurta(valor: string): string {
  return new Date(valor).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" });
}

/** Painel de créditos de ENRIQUECIMENTO (pesquisa de decisores) do tenant. Separado dos créditos de IA. O orçamento global do provedor só aparece
 * para o super administrador. */
export function CreditosEnriquecimento() {
  const { usuario } = useAuth();
  const gestor = usuario?.papel === "admin" || usuario?.papel === "super_admin";
  const superAdmin = usuario?.papel === "super_admin";
  const [painel, setPainel] = useState<Painel | null>(null);
  const [pesquisas, setPesquisas] = useState<PesquisaResumo[]>([]);
  const [movimentos, setMovimentos] = useState<Movimento[]>([]);
  const [tipo, setTipo] = useState("");
  const [admin, setAdmin] = useState<VisaoAdmin | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [limite, setLimite] = useState("");
  const [motivo, setMotivo] = useState("");
  const [salvando, setSalvando] = useState(false);
  const [aviso, setAviso] = useState<string | null>(null);

  useEffect(() => {
    api.get<Painel>("/pesquisas-decisores/painel").then(setPainel).catch((e) => setErro(mensagemErro(e, "Não foi possível carregar o painel.")));
    api.get<PesquisaResumo[]>("/pesquisas-decisores?limite=20").then(setPesquisas).catch(() => setPesquisas([]));
  }, []);

  useEffect(() => {
    if (!gestor) return;
    const filtro = tipo ? `?tipo=${tipo}&limite=50` : "?limite=50";
    api.get<Movimento[]>(`/pesquisas-decisores/movimentacoes${filtro}`).then(setMovimentos).catch(() => setMovimentos([]));
  }, [gestor, tipo]);

  function carregarAdmin() {
    api.get<VisaoAdmin>("/admin/enriquecimento/orcamento-global?provedor=lusha").then(setAdmin).catch(() => setAdmin(null));
  }
  useEffect(() => {
    if (superAdmin) carregarAdmin();
  }, [superAdmin]);

  async function salvarOrcamento(evento: FormEvent) {
    evento.preventDefault();
    setSalvando(true);
    setAviso(null);
    try {
      await api.put("/admin/enriquecimento/orcamento-global", {
        provedor: "lusha",
        limite_creditos: limite.trim() === "" ? null : Number(limite),
        alerta_percentual: 80,
        motivo,
      });
      setAviso("Orçamento global atualizado (nova versão, auditada).");
      setMotivo("");
      carregarAdmin();
    } catch (e) {
      setAviso(mensagemErro(e, "Não foi possível atualizar o orçamento global."));
    } finally {
      setSalvando(false);
    }
  }

  if (erro) return <div className="p-5.5 text-red">{erro}</div>;
  if (!painel) return <div className="p-5.5 text-muted">Carregando...</div>;

  const p = painel.plano;
  return (
    <div className="space-y-3.5 p-5.5">
      <div>
        <h1 className="font-head text-[18px] font-bold">Créditos de enriquecimento</h1>
        <p className="text-[12px] text-muted">
          Cada decisor revelado pelo provedor consome 1 crédito. É uma conta separada dos créditos de IA. Período {painel.periodo}.
        </p>
      </div>

      {painel.alertas.map((a) => (
        <div key={a.codigo} className="rounded-md bg-surf2 p-2 text-[12px] text-amber">
          {a.mensagem}
        </div>
      ))}

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
        <KpiCard label="Disponível" value={painel.creditos.disponivel} sub="saldo − reservado" />
        <KpiCard label="Reservado" value={painel.creditos.reservado} sub="pesquisas em curso" colorClassName="text-amber" />
        <KpiCard label="Consumido no período" value={painel.creditos.consumido_no_periodo} colorClassName="text-green" />
        <KpiCard label="Concedido no período" value={painel.creditos.concedido_no_periodo} colorClassName="text-violet" />
        <KpiCard label="Expirado no período" value={painel.creditos.expirado_no_periodo} colorClassName="text-muted" />
      </div>

      <Card>
        <SectionLabel>Seu plano</SectionLabel>
        {p.disponivel ? (
          <dl className="grid grid-cols-2 gap-2 text-[12px] lg:grid-cols-4">
            <Item rotulo="Franquia" valor={`${p.franquia_creditos ?? "—"} (${p.periodicidade === "unica" ? "única" : "mensal"})`} />
            <Item rotulo="Decisores por empresa" valor={`padrão ${p.decisores_por_empresa_padrao}, máx. ${p.decisores_por_empresa_max}`} />
            <Item rotulo="Empresas por pesquisa" valor={`até ${p.itens_por_lote_max}`} />
            <Item rotulo="Limite no período" valor={p.limite_periodo_creditos == null ? "sem teto extra" : String(p.limite_periodo_creditos)} />
          </dl>
        ) : (
          <p className="text-[12px] text-amber">
            {p.orientacao ?? "A pesquisa de decisores não está liberada no seu plano."}
            {p.faltando && p.faltando.length > 0 ? ` (faltando: ${p.faltando.join(", ")})` : ""}
          </p>
        )}
        <p className="mt-2 text-[11px] text-muted">
          Estimado no máximo nas pesquisas concluídas: {painel.estimado_vs_reconciliado.estimado_maximo} · consumido de fato: {painel.estimado_vs_reconciliado.consumido}
        </p>
      </Card>

      <Card>
        <SectionLabel>Pesquisas por estado</SectionLabel>
        <div className="mb-2 flex flex-wrap gap-2">
          {Object.entries(painel.pesquisas_por_estado).map(([estado, total]) => (
            <Badge key={estado} tone={estado === "concluida" ? "green" : estado === "em_processamento" ? "amber" : "muted"}>
              {estado}: {total}
            </Badge>
          ))}
          {Object.keys(painel.pesquisas_por_estado).length === 0 && <span className="text-[12px] text-muted">Nenhuma pesquisa ainda. Selecione contas em Prospecção e use “Pesquisar decisores”.</span>}
        </div>
        <table className="w-full border-collapse text-[12px]">
          <tbody>
            {pesquisas.map((x) => (
              <tr key={x.id} className="border-b border-border">
                <td className="p-1.5 text-muted">{dataCurta(x.criado_em)}</td>
                <td className="p-1.5">{x.total_empresas} empresa(s) × {x.decisores_por_empresa}</td>
                <td className="p-1.5">
                  <Badge tone={x.requer_reconciliacao ? "amber" : x.estado === "concluida" ? "green" : "muted"}>{x.estado}</Badge>
                </td>
                <td className="p-1.5 text-right text-muted">
                  {x.creditos_consumidos} / até {x.total_maximo}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>

      {gestor && (
        <Card>
          <div className="mb-2 flex items-center justify-between gap-2">
            <SectionLabel className="mb-0">Extrato</SectionLabel>
            <Select value={tipo} onChange={(ev) => setTipo(ev.target.value)}>
              {TIPOS.map((t) => (
                <option key={t} value={t}>
                  {t || "Todos os tipos"}
                </option>
              ))}
            </Select>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full border-collapse text-[12px]">
              <thead>
                <tr className="border-b border-border text-[9.5px] tracking-wide text-muted uppercase">
                  <th className="p-1.5 text-left">Quando</th>
                  <th className="p-1.5 text-left">Tipo</th>
                  <th className="p-1.5 text-right">Saldo</th>
                  <th className="p-1.5 text-right">Reservado</th>
                  <th className="p-1.5 text-right">Disponível após</th>
                  <th className="p-1.5 text-left">Motivo</th>
                </tr>
              </thead>
              <tbody>
                {movimentos.map((m) => (
                  <tr key={m.id} className="border-b border-border">
                    <td className="p-1.5 whitespace-nowrap text-muted">{dataCurta(m.criado_em)}</td>
                    <td className="p-1.5">{m.tipo}</td>
                    <td className="p-1.5 text-right tabular-nums">{m.delta_saldo > 0 ? `+${m.delta_saldo}` : m.delta_saldo}</td>
                    <td className="p-1.5 text-right tabular-nums">{m.delta_reservado > 0 ? `+${m.delta_reservado}` : m.delta_reservado}</td>
                    <td className="p-1.5 text-right tabular-nums">{m.disponivel_apos}</td>
                    <td className="p-1.5 text-muted">{m.motivo ?? m.origem ?? ""}</td>
                  </tr>
                ))}
                {movimentos.length === 0 && (
                  <tr>
                    <td colSpan={6} className="p-3 text-center text-muted">
                      Sem movimentações.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {superAdmin && admin && (
        <Card>
          <SectionLabel>Administração — orçamento global do provedor ({admin.orcamento_global.provedor})</SectionLabel>
          <div className="mb-2 flex flex-wrap items-center gap-2 text-[12px]">
            <Badge tone={NIVEL_TOM[admin.orcamento_global.nivel] ?? "muted"}>{NIVEL_ROTULO[admin.orcamento_global.nivel] ?? admin.orcamento_global.nivel}</Badge>
            {admin.orcamento_global.limite !== null && (
              <span className="text-muted">
                limite {admin.orcamento_global.limite} · consumido {admin.orcamento_global.consumido} · reservado {admin.orcamento_global.reservado} · restante {admin.orcamento_global.restante}
              </span>
            )}
          </div>
          <form onSubmit={salvarOrcamento} className="flex flex-wrap items-end gap-2">
            <Input label="Limite mensal (créditos)" type="number" min={0} value={limite} onChange={(ev) => setLimite(ev.target.value)} placeholder="vazio = não configurado" />
            <Input label="Motivo (auditado)" value={motivo} onChange={(ev) => setMotivo(ev.target.value)} placeholder="ex.: contrato ampliado em 20/10" />
            <Button size="sm" type="submit" disabled={salvando || motivo.trim().length < 3}>
              {salvando ? "Salvando..." : "Definir nova versão"}
            </Button>
          </form>
          {aviso && <p className="mt-1.5 text-[12px] text-muted">{aviso}</p>}
          {admin.pendentes_reconciliacao.length > 0 && (
            <div className="mt-3">
              <p className="mb-1 text-[12px] font-semibold text-amber">Aguardando reconciliação com o provedor</p>
              <ul className="space-y-0.5 text-[12px]">
                {admin.pendentes_reconciliacao.map((r) => (
                  <li key={r.pesquisa_id} className="text-muted">
                    {r.tenant_id} · pesquisa {r.pesquisa_id.slice(0, 8)} · {r.empresas_ambiguas} empresa(s) ambígua(s) · {r.creditos_reservados} crédito(s) retido(s). Reconcilie pela API
                    administrativa com o uso informado pelo provedor.
                  </li>
                ))}
              </ul>
            </div>
          )}
        </Card>
      )}
    </div>
  );
}

function Item({ rotulo, valor }: { rotulo: string; valor: string }) {
  return (
    <div>
      <dt className="text-[9.5px] tracking-wide text-muted uppercase">{rotulo}</dt>
      <dd className="font-semibold">{valor}</dd>
    </div>
  );
}
