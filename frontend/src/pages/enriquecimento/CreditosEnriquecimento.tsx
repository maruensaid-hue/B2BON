import { useEffect, useState, type FormEvent } from "react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, SectionLabel } from "@/components/ui/Card";
import { Input, Select } from "@/components/ui/Input";
import { KpiCard } from "@/components/ui/KpiCard";
import { api, mensagemErro } from "@/lib/api";
import { useAuth } from "@/lib/auth";

import { AdminCustoVendas } from "./AdminCustoVendas";
import { AdminEnriquecimento } from "./AdminEnriquecimento";
import { custoCredito, dataExpiracao, dataVencimento } from "./formatos";
import { PacotesAdicionais } from "./PacotesAdicionais";

interface Painel {
  periodo: string;
  plano: {
    disponivel: boolean;
    origem?: string;
    versao?: number;
    faltando?: string[];
    modo?: string;
    franquia_creditos?: number | null;
    periodicidade?: string | null;
    decisores_por_empresa_padrao?: number | null;
    decisores_por_empresa_max?: number | null;
    itens_por_lote_max?: number | null;
    limite_periodo_creditos?: number | null;
    limite_creditos_pesquisa?: number | null;
    limite_origem?: string;
    limite_pesquisas_periodo?: number | null;
    limite_empresas_periodo?: number | null;
    limite_contatos_periodo?: number | null;
    orientacao?: string | null;
  };
  contatos: { disponivel: boolean; motivos: { codigo: string; mensagem: string }[] };
  categorias: { ia: string; enriquecimento: string };
  creditos: {
    disponivel: number;
    reservado: number;
    saldo: number;
    consumido_no_periodo: number;
    expirado_no_periodo: number;
    concedido_no_periodo: number;
    comprado_no_periodo: number;
  };
  composicao: {
    franquia_restante: number;
    adicional_restante: number;
    outros: number;
    saldo: number;
    expira_em: string;
    acumula: boolean;
    adicional_expira_em: string | null;
    pacotes_ativos: { creditos: number; restante: number; expira_em: string | null }[];
  };
  uso_no_periodo: { pesquisas: number; empresas: number; contatos: number };
  compra_adicional: { disponivel: boolean; motivos: { codigo: string; mensagem: string }[] };
  uso_por_fonte: Record<string, number>;
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
  creditos_provedor: number | null;
  fonte: string | null;
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
  provedor_consumidos: number;
  requer_reconciliacao: boolean;
  criado_em: string;
}

interface Politica {
  vigente: boolean;
  motivo?: string;
  versao?: number;
  utilizavel?: boolean;
  custo_unitario_brl?: string;
  markup_percentual?: string;
  preco_unitario_brl?: string;
  preco_unitario_exibicao?: string;
  margem_bruta_percentual?: string;
  creditos_cliente_por_credito_provedor?: number;
}

interface Resultado {
  custo_brl: string;
  venda_brl: string;
  margem_brl: string;
  margem_percentual: string | null;
}

interface VisaoAdmin {
  orcamento_global: { provedor: string; nivel: string; limite: number | null; consumido: number; reservado: number; restante: number | null; percentual: number | null };
  orcamento_pendente_aprovacao: boolean;
  politica: Politica | null;
  resultado_financeiro: { mes: Resultado; total: Resultado };
  lotes_compra: { id: number; referencia: string; quantidade_creditos: number; custo_total_brl: string; custo_unitario_brl: string }[];
  leituras_de_uso: { id: number; lido_em: string; creditos_usados: number | null; delta_provedor: number | null; delta_razao: number | null; divergencia: number | null; explicacao: string }[];
  aprovacoes_pendentes: { configs: number; politicas: number; orcamentos: number };
  pendentes_reconciliacao: { pesquisa_id: string; tenant_id: string; estado: string; empresas_ambiguas: number; creditos_provedor_reservados: number }[];
}

const TIPOS = ["", "CONCESSAO", "RENOVACAO", "COMPRA", "RESERVA", "CONSUMO", "LIBERACAO", "ESTORNO", "EXPIRACAO", "AJUSTE", "RECONCILIACAO", "USO"];
const ROTULO_FONTE: Record<string, string> = { receita_qsa: "QSA da Receita", cadastro_publico: "Dados cadastrais públicos", contatos: "Decisores" };

const NIVEL_TOM: Record<string, "green" | "amber" | "red" | "muted"> = { ok: "green", alerta: "amber", esgotado: "red", nao_configurado: "red" };
const NIVEL_ROTULO: Record<string, string> = {
  ok: "Dentro do limite", alerta: "Perto do limite", esgotado: "Esgotado", nao_configurado: "Sem orçamento aprovado — chamadas ao provedor bloqueadas",
};

function dataCurta(valor: string): string {
  return new Date(valor).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" });
}

function brl(valor: string): string {
  return `R$ ${Number(valor).toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 4 })}`;
}

/** Painel de créditos de ENRIQUECIMENTO (pesquisa de decisores) do tenant. Separado dos créditos de IA. Orçamento global, custo, markup e margem só
 * aparecem para o super administrador. */
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
  const [pendenteId, setPendenteId] = useState<number | null>(null);
  const [conciliando, setConciliando] = useState(false);

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
    api.get<VisaoAdmin>("/admin/enriquecimento/orcamento-global?provedor=contatos").then(setAdmin).catch(() => setAdmin(null));
  }
  useEffect(() => {
    if (superAdmin) carregarAdmin();
  }, [superAdmin]);

  async function salvarOrcamento(evento: FormEvent) {
    evento.preventDefault();
    setSalvando(true);
    setAviso(null);
    try {
      const nova = await api.put<{ id: number; versao: number }>("/admin/enriquecimento/orcamento-global", {
        provedor: "contatos",
        limite_creditos: limite.trim() === "" ? null : Number(limite),
        alerta_percentual: 80,
        motivo,
      });
      setPendenteId(nova.id);
      setAviso(`Versão ${nova.versao} criada e PENDENTE de aprovação. Ela só passa a valer depois de aprovada.`);
      setMotivo("");
      carregarAdmin();
    } catch (e) {
      setAviso(mensagemErro(e, "Não foi possível criar a versão do orçamento global."));
    } finally {
      setSalvando(false);
    }
  }

  async function aprovarOrcamento() {
    if (pendenteId === null) return;
    setSalvando(true);
    try {
      await api.post(`/admin/enriquecimento/orcamento-global/${pendenteId}/aprovar`, {});
      setPendenteId(null);
      setAviso("Orçamento global aprovado (auditado).");
      carregarAdmin();
    } catch (e) {
      setAviso(mensagemErro(e, "Não foi possível aprovar."));
    } finally {
      setSalvando(false);
    }
  }

  async function conciliar() {
    setConciliando(true);
    setAviso(null);
    try {
      const leitura = await api.post<{ explicacao: string }>("/admin/enriquecimento/provedores/contatos/conciliar", {});
      setAviso(leitura.explicacao);
      carregarAdmin();
    } catch (e) {
      setAviso(mensagemErro(e, "Não foi possível conciliar com o provedor."));
    } finally {
      setConciliando(false);
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
          Pesquisa de decisores em provedor pago. O consumo é o medido pelo provedor. Esta é uma conta separada dos créditos de IA. {painel.categorias.ia} Período {painel.periodo}.
        </p>
      </div>

      <Card>
        <SectionLabel>Pesquisa de decisores</SectionLabel>
        {painel.contatos.disponivel ? (
          <p className="text-[12px] text-green">Disponível para o seu plano.</p>
        ) : (
          <div className="text-[12px] text-amber">
            <p className="mb-1 font-semibold">Indisponível agora. Motivo:</p>
            <ul className="list-disc space-y-0.5 pl-4">
              {painel.contatos.motivos.map((m) => (
                <li key={m.codigo}>{m.mensagem}</li>
              ))}
            </ul>
          </div>
        )}
        <p className="mt-1 text-[11px] text-muted">O mapeamento de decisores pelo QSA da Receita e o enriquecimento por dados cadastrais públicos não dependem desta liberação.</p>
      </Card>

      {painel.alertas
        .filter((a) => a.codigo !== "pesquisa_indisponivel")
        .map((a) => (
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
        <SectionLabel>Saldo e validade</SectionLabel>
        <dl className="grid grid-cols-2 gap-2 text-[12px] lg:grid-cols-4">
          <Item rotulo="Franquia do mês (restante)" valor={String(painel.composicao.franquia_restante)} />
          <Item rotulo="Créditos adicionais (restante)" valor={String(painel.composicao.adicional_restante)} />
          {painel.composicao.outros !== 0 && <Item rotulo="Autorização / ajuste" valor={String(painel.composicao.outros)} />}
          <Item rotulo="Franquia vence em" valor={dataExpiracao(painel.composicao.expira_em)} />
          {painel.composicao.adicional_expira_em && <Item rotulo="Adicionais vencem em" valor={dataVencimento(painel.composicao.adicional_expira_em)} />}
        </dl>
        <p className="mt-1 text-[11px] text-muted">
          A franquia vence no fim do mês e os créditos adicionais valem 30 dias a partir da confirmação do pagamento; nenhum dos dois acumula. Ao consumir, usa-se primeiro o que
          vence antes (a franquia).
          {painel.composicao.pacotes_ativos.length > 0 &&
            " Enquanto houver crédito de pacote válido, o seu limite de créditos por pesquisa é o do pacote; depois volta ao do plano."}
        </p>
      </Card>

      <Card>
        <SectionLabel>Seu plano</SectionLabel>
        {p.disponivel ? (
          <dl className="grid grid-cols-2 gap-2 text-[12px] lg:grid-cols-4">
            {p.modo === "poc_autorizada" ? (
              <Item rotulo="Franquia" valor="POC: sem franquia fixa" />
            ) : (
              <Item rotulo="Franquia" valor={`${p.franquia_creditos ?? "—"} (${p.periodicidade === "unica" ? "única" : "mensal"})`} />
            )}
            <Item
              rotulo="Créditos por pesquisa"
              valor={
                p.limite_creditos_pesquisa == null
                  ? p.limite_origem === "super_admin"
                    ? "sem limite"
                    : "—"
                  : `até ${p.limite_creditos_pesquisa}${p.limite_origem === "pacote" ? " (pacote adicional)" : ""}`
              }
            />
            <Item
              rotulo="Decisores por empresa"
              valor={p.decisores_por_empresa_padrao ? `padrão ${p.decisores_por_empresa_padrao}, máx. ${p.decisores_por_empresa_max}` : `você escolhe, máx. ${p.decisores_por_empresa_max}`}
            />
            <Item rotulo="Empresas por pesquisa" valor={p.itens_por_lote_max == null ? "sem limite fixo" : `até ${p.itens_por_lote_max}`} />
            <Item rotulo="Limite no período" valor={p.limite_periodo_creditos == null ? "sem teto extra" : String(p.limite_periodo_creditos)} />
            {p.limite_pesquisas_periodo != null && <Item rotulo="Pesquisas no mês" valor={`${painel.uso_no_periodo.pesquisas} de ${p.limite_pesquisas_periodo}`} />}
            {p.limite_empresas_periodo != null && <Item rotulo="Empresas no mês" valor={`${painel.uso_no_periodo.empresas} de ${p.limite_empresas_periodo}`} />}
            {p.limite_contatos_periodo != null && <Item rotulo="Contatos no mês" valor={`${painel.uso_no_periodo.contatos} de ${p.limite_contatos_periodo}`} />}
          </dl>
        ) : (
          <p className="text-[12px] text-amber">
            {p.orientacao ?? "A pesquisa de decisores não está liberada no seu plano."}
            {p.faltando && p.faltando.length > 0 ? ` (faltando: ${p.faltando.join(", ")})` : ""}
          </p>
        )}
        <p className="mt-2 text-[11px] text-muted">
          Teto estimado nas pesquisas concluídas: {painel.estimado_vs_reconciliado.estimado_maximo} · consumido de fato: {painel.estimado_vs_reconciliado.consumido}
        </p>
        {Object.keys(painel.uso_por_fonte).length > 0 && (
          <p className="mt-1 text-[11px] text-muted">
            Uso por fonte no período (sem custo de crédito):{" "}
            {Object.entries(painel.uso_por_fonte)
              .map(([fonte, total]) => `${ROTULO_FONTE[fonte] ?? fonte}: ${total}`)
              .join(" · ")}
          </p>
        )}
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
                  {x.creditos_consumidos} / teto {x.total_maximo}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>

      {gestor && <PacotesAdicionais />}

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
                  <th className="p-1.5 text-right">Créd. provedor</th>
                  <th className="p-1.5 text-right">Disponível após</th>
                  <th className="p-1.5 text-left">Motivo</th>
                </tr>
              </thead>
              <tbody>
                {movimentos.map((m) => (
                  <tr key={m.id} className="border-b border-border">
                    <td className="p-1.5 whitespace-nowrap text-muted">{dataCurta(m.criado_em)}</td>
                    <td className="p-1.5">{m.tipo}{m.fonte ? ` · ${ROTULO_FONTE[m.fonte] ?? m.fonte}` : ""}</td>
                    <td className="p-1.5 text-right tabular-nums">{m.delta_saldo > 0 ? `+${m.delta_saldo}` : m.delta_saldo}</td>
                    <td className="p-1.5 text-right tabular-nums">{m.delta_reservado > 0 ? `+${m.delta_reservado}` : m.delta_reservado}</td>
                    <td className="p-1.5 text-right tabular-nums">{m.creditos_provedor ?? ""}</td>
                    <td className="p-1.5 text-right tabular-nums">{m.disponivel_apos}</td>
                    <td className="p-1.5 text-muted">{m.motivo ?? m.origem ?? ""}</td>
                  </tr>
                ))}
                {movimentos.length === 0 && (
                  <tr>
                    <td colSpan={7} className="p-3 text-center text-muted">
                      Sem movimentações.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {superAdmin && <AdminEnriquecimento />}

      {superAdmin && <AdminCustoVendas />}

      {superAdmin && admin && (
        <Card>
          <SectionLabel>Administração — provedor de contatos (visível só ao super administrador)</SectionLabel>
          <div className="mb-2 flex flex-wrap items-center gap-2 text-[12px]">
            <Badge tone={NIVEL_TOM[admin.orcamento_global.nivel] ?? "muted"}>{NIVEL_ROTULO[admin.orcamento_global.nivel] ?? admin.orcamento_global.nivel}</Badge>
            {admin.orcamento_global.limite !== null && (
              <span className="text-muted">
                orçamento global: limite {admin.orcamento_global.limite} · consumido {admin.orcamento_global.consumido} · reservado {admin.orcamento_global.reservado} · restante {admin.orcamento_global.restante} (créditos do provedor)
              </span>
            )}
            {admin.orcamento_pendente_aprovacao && <Badge tone="amber">há versão do orçamento pendente de aprovação</Badge>}
          </div>

          {admin.politica?.vigente ? (
            <dl className="mb-3 grid grid-cols-2 gap-2 text-[12px] lg:grid-cols-4">
              <Item rotulo="Custo por crédito (contrato)" valor={custoCredito(admin.politica.custo_unitario_brl ?? "0")} />
              <Item rotulo="Markup" valor={`${Number(admin.politica.markup_percentual)}%`} />
              <Item rotulo="Preço de venda por crédito" valor={`${custoCredito(admin.politica.preco_unitario_brl ?? "0")} (≈ R$ ${admin.politica.preco_unitario_exibicao?.replace(".", ",")})`} />
              <Item rotulo="Margem bruta s/ venda" valor={`${Number(admin.politica.margem_bruta_percentual)}%`} />
            </dl>
          ) : (
            <p className="mb-3 text-[12px] text-amber">Política do provedor sem versão aprovada ({admin.politica?.motivo ?? "não configurada"}): a pesquisa de decisores permanece bloqueada.</p>
          )}

          <div className="mb-3 grid grid-cols-1 gap-2 text-[12px] lg:grid-cols-2">
            <div className="rounded-md bg-surf2 p-2">
              <p className="font-semibold">Resultado no mês</p>
              <p className="text-muted">
                custo {brl(admin.resultado_financeiro.mes.custo_brl)} · venda {brl(admin.resultado_financeiro.mes.venda_brl)} · margem {brl(admin.resultado_financeiro.mes.margem_brl)}
                {admin.resultado_financeiro.mes.margem_percentual ? ` (${Number(admin.resultado_financeiro.mes.margem_percentual)}%)` : ""}
              </p>
            </div>
            <div className="rounded-md bg-surf2 p-2">
              <p className="font-semibold">Lotes de compra</p>
              {admin.lotes_compra.map((l) => (
                <p key={l.id} className="text-muted">
                  {l.referencia}: {l.quantidade_creditos} créditos por {brl(l.custo_total_brl)} (custo unitário {brl(l.custo_unitario_brl)})
                </p>
              ))}
              {admin.lotes_compra.length === 0 && <p className="text-muted">Nenhum lote registrado.</p>}
            </div>
          </div>

          <div className="mb-3 flex flex-wrap items-center gap-2 text-[12px]">
            <Button size="sm" variant="ghost" disabled={conciliando} onClick={conciliar}>
              {conciliando ? "Conciliando..." : "Conciliar com o uso do provedor"}
            </Button>
            {admin.leituras_de_uso[0] && (
              <span className={admin.leituras_de_uso[0].divergencia ? "text-amber" : "text-muted"}>
                Última leitura em {dataCurta(admin.leituras_de_uso[0].lido_em)}: {admin.leituras_de_uso[0].explicacao}
              </span>
            )}
          </div>

          <p className="mb-1 text-[11px] text-muted">
            Aprovações pendentes — planos: {admin.aprovacoes_pendentes.configs} · política: {admin.aprovacoes_pendentes.politicas} · orçamento: {admin.aprovacoes_pendentes.orcamentos}. Configuração por plano,
            política e lotes são feitos pela API administrativa; cada versão nova nasce pendente e só vale depois de aprovada.
          </p>
          <form onSubmit={salvarOrcamento} className="flex flex-wrap items-end gap-2">
            <Input label="Limite mensal (créditos do provedor)" type="number" min={0} value={limite} onChange={(ev) => setLimite(ev.target.value)} placeholder="vazio = não configurado" />
            <Input label="Motivo (auditado)" value={motivo} onChange={(ev) => setMotivo(ev.target.value)} placeholder="ex.: contrato ampliado em 20/10" />
            <Button size="sm" type="submit" disabled={salvando || motivo.trim().length < 3}>
              {salvando ? "Salvando..." : "Criar versão do orçamento"}
            </Button>
            {pendenteId !== null && (
              <Button size="sm" variant="ghost" disabled={salvando} onClick={aprovarOrcamento}>
                Aprovar a versão criada
              </Button>
            )}
          </form>
          {aviso && <p className="mt-1.5 text-[12px] text-muted">{aviso}</p>}
          {admin.pendentes_reconciliacao.length > 0 && (
            <div className="mt-3">
              <p className="mb-1 text-[12px] font-semibold text-amber">Aguardando reconciliação com o provedor</p>
              <ul className="space-y-0.5 text-[12px]">
                {admin.pendentes_reconciliacao.map((r) => (
                  <li key={r.pesquisa_id} className="text-muted">
                    {r.tenant_id} · pesquisa {r.pesquisa_id.slice(0, 8)} · {r.empresas_ambiguas} empresa(s) ambígua(s) · {r.creditos_provedor_reservados} crédito(s) do provedor retido(s). Reconcilie pela API
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
