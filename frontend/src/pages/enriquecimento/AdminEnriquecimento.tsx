import { useCallback, useEffect, useState, type FormEvent } from "react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, SectionLabel } from "@/components/ui/Card";
import { Input, Select } from "@/components/ui/Input";
import { api, mensagemErro } from "@/lib/api";

import { reais } from "./formatos";

interface LinhaMatriz {
  matriz: string;
  plano: string | null;
  situacao: string;
}

interface PlanoStatus {
  plano_id: number;
  plano: string;
  situacao: string;
  modo: string | null;
}

interface ConfigLinha {
  id: number;
  plano_id: number | null;
  tenant_id: string | null;
  versao: number;
  modo: string;
  franquia_creditos: number | null;
  periodicidade: string | null;
  decisores_por_empresa_padrao: number | null;
  decisores_por_empresa_max: number | null;
  itens_por_lote_max: number | null;
  limite_creditos_pesquisa: number | null;
  limite_pesquisas_periodo: number | null;
  limite_empresas_periodo: number | null;
  limite_contatos_periodo: number | null;
  aprovada: boolean;
  faltando: string[];
  motivo: string | null;
}

interface PacoteLinha {
  id: number;
  codigo: string;
  versao: number;
  creditos: number | null;
  status: string;
  preco_unitario_brl: string | null;
  preco_total_brl: string | null;
  aprovado: boolean;
  valido_ate: string | null;
}

interface Rentabilidade {
  custo_unitario_provedor_brl: string | null;
  origem_custo: string | null;
  creditos_cliente_por_credito_provedor: number;
  premissa_fator: boolean;
  pacotes: { codigo: string; creditos: number | null; status: string; preco_total_brl?: string; custo_total_brl?: string; lucro_bruto_brl?: string; markup_percentual?: string; margem_bruta_percentual?: string }[];
}

interface CompraAdmin {
  id: number;
  tenant_id: string;
  pacote: string;
  creditos: number;
  preco_total_brl: string;
  status: string;
  criado_em: string;
}

interface Auditoria {
  id: number;
  tenant_id: string;
  evento: string;
  entidade_id: number;
  ator_id: string | null;
  criado_em: string;
}

interface Teto {
  empresas: number;
  decisores_por_empresa: number;
  creditos_provedor_teto: number;
  creditos_cliente_teto: number;
  custo_maximo_brl: string;
  valor_venda_maximo_brl: string;
  aviso: string;
}

const SITUACAO_MATRIZ: Record<string, { rotulo: string; tom: "green" | "amber" | "red" | "muted" }> = {
  aplicada: { rotulo: "aplicada", tom: "green" },
  nao_aplicada: { rotulo: "ainda não aplicada", tom: "amber" },
  diverge_da_matriz: { rotulo: "diverge da matriz", tom: "red" },
  plano_inexistente: { rotulo: "sem plano correspondente", tom: "muted" },
  configuravel_por_administrador: { rotulo: "configurada por tenant", tom: "muted" },
};

const CONFIG_VAZIA = {
  alvo: "plano", plano_id: "", tenant_id: "", modo: "franquia_fixa", franquia_creditos: "", periodicidade: "mensal", decisores_por_empresa_padrao: "",
  decisores_por_empresa_max: "", itens_por_lote_max: "", limite_creditos_pesquisa: "", limite_pesquisas_periodo: "", limite_empresas_periodo: "",
  limite_contatos_periodo: "", motivo: "",
};

function numero(valor: string): number | null {
  return valor.trim() === "" ? null : Number(valor);
}

function percentual(valor: string): string {
  return `${Number(valor).toLocaleString("pt-BR", { maximumFractionDigits: 1 })}%`;
}

function custoCredito(valor: string): string {
  return `R$ ${Number(valor).toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 5 })}`;
}

function dataCurta(valor: string): string {
  return new Date(valor.endsWith("Z") ? valor : `${valor}Z`).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" });
}

/** Administração dos créditos de enriquecimento (somente super administrador): matriz de franquias, configuração por plano ou tenant, pacotes e
 * rentabilidade, lotes de compra, POC, compras e auditoria. Toda alteração nasce PENDENTE e só vale depois de aprovada. */
export function AdminEnriquecimento() {
  const [matriz, setMatriz] = useState<LinhaMatriz[]>([]);
  const [planos, setPlanos] = useState<PlanoStatus[]>([]);
  const [mapeamento, setMapeamento] = useState<Record<string, string>>({});
  const [configs, setConfigs] = useState<ConfigLinha[]>([]);
  const [pacotes, setPacotes] = useState<PacoteLinha[]>([]);
  const [rentabilidade, setRentabilidade] = useState<Rentabilidade | null>(null);
  const [compras, setCompras] = useState<CompraAdmin[]>([]);
  const [auditoria, setAuditoria] = useState<Auditoria[]>([]);
  const [aviso, setAviso] = useState<string | null>(null);
  const [form, setForm] = useState(CONFIG_VAZIA);
  const [lote, setLote] = useState({ referencia: "", quantidade: "", custo: "", data: "" });
  const [poc, setPoc] = useState({ empresas: "", decisores: "1", tenant: "", motivo: "" });
  const [teto, setTeto] = useState<Teto | null>(null);
  const [ocupado, setOcupado] = useState(false);

  const carregar = useCallback(() => {
    api.get<LinhaMatriz[]>("/admin/enriquecimento/matriz").then(setMatriz).catch(() => setMatriz([]));
    api.get<PlanoStatus[]>("/admin/enriquecimento/planos").then(setPlanos).catch(() => setPlanos([]));
    api.get<ConfigLinha[]>("/admin/enriquecimento/config").then(setConfigs).catch(() => setConfigs([]));
    api.get<PacoteLinha[]>("/admin/enriquecimento/pacotes").then(setPacotes).catch(() => setPacotes([]));
    api.get<Rentabilidade>("/admin/enriquecimento/pacotes/rentabilidade?provedor=lusha").then(setRentabilidade).catch(() => setRentabilidade(null));
    api.get<CompraAdmin[]>("/admin/enriquecimento/compras?limite=20").then(setCompras).catch(() => setCompras([]));
    api.get<Auditoria[]>("/admin/enriquecimento/auditoria?limite=30").then(setAuditoria).catch(() => setAuditoria([]));
  }, []);
  useEffect(carregar, [carregar]);

  async function executar(acao: () => Promise<string>) {
    setOcupado(true);
    setAviso(null);
    try {
      setAviso(await acao());
      carregar();
    } catch (e) {
      setAviso(mensagemErro(e, "A operação não foi concluída."));
    } finally {
      setOcupado(false);
    }
  }

  function aplicarMatriz() {
    const escolhido = Object.fromEntries(Object.entries(mapeamento).filter(([, v]) => v !== "").map(([k, v]) => [k, Number(v)]));
    executar(async () => {
      const r = await api.post<{ aplicados: { plano: string; versao: number }[]; inalterados: string[]; nao_encontrados: string[]; ajustes: unknown[] }>(
        "/admin/enriquecimento/matriz/aplicar",
        { mapeamento: escolhido },
      );
      return `Aplicados: ${r.aplicados.map((a) => `${a.plano} (v${a.versao})`).join(", ") || "nenhum"} · já conforme: ${r.inalterados.join(", ") || "nenhum"} · sem plano: ${r.nao_encontrados.join(", ") || "nenhum"}${r.ajustes.length ? ` · ${r.ajustes.length} ajuste(s) de padrão de decisores` : ""}.`;
    });
  }

  function salvarConfig(evento: FormEvent) {
    evento.preventDefault();
    executar(async () => {
      const corpo: Record<string, unknown> = {
        plano_id: form.alvo === "plano" ? numero(form.plano_id) : null,
        tenant_id: form.alvo === "tenant" ? form.tenant_id.trim() : null,
        modo: form.modo,
        franquia_creditos: numero(form.franquia_creditos),
        periodicidade: form.periodicidade || null,
        decisores_por_empresa_padrao: numero(form.decisores_por_empresa_padrao),
        decisores_por_empresa_max: numero(form.decisores_por_empresa_max),
        itens_por_lote_max: numero(form.itens_por_lote_max),
        limite_creditos_pesquisa: numero(form.limite_creditos_pesquisa),
        limite_pesquisas_periodo: numero(form.limite_pesquisas_periodo),
        limite_empresas_periodo: numero(form.limite_empresas_periodo),
        limite_contatos_periodo: numero(form.limite_contatos_periodo),
        motivo: form.motivo,
      };
      const nova = await api.put<ConfigLinha>("/admin/enriquecimento/config", corpo);
      setForm(CONFIG_VAZIA);
      return `Versão ${nova.versao} criada e PENDENTE de aprovação${nova.faltando.length ? ` (faltando: ${nova.faltando.join(", ")})` : ""}.`;
    });
  }

  function registrarLote(evento: FormEvent) {
    evento.preventDefault();
    executar(async () => {
      await api.post("/admin/enriquecimento/lotes-compra", {
        provedor: "lusha",
        referencia: lote.referencia,
        quantidade_creditos: Number(lote.quantidade),
        custo_total_brl: lote.custo.replace(",", "."),
        comprado_em: new Date(lote.data || Date.now()).toISOString(),
      });
      setLote({ referencia: "", quantidade: "", custo: "", data: "" });
      return "Lote registrado. Um novo aporte nunca sobrescreve os anteriores; o preço só muda com uma nova política aprovada.";
    });
  }

  function calcularTeto(evento: FormEvent) {
    evento.preventDefault();
    executar(async () => {
      setTeto(await api.post<Teto>("/admin/enriquecimento/poc/teto", { empresas: Number(poc.empresas), decisores_por_empresa: Number(poc.decisores) }));
      return "Teto calculado com as tarifas aprovadas (nada foi gravado).";
    });
  }

  function autorizarPoc() {
    executar(async () => {
      await api.post("/admin/enriquecimento/poc/autorizar", {
        tenant_id: poc.tenant.trim(),
        empresas: Number(poc.empresas),
        decisores_por_empresa: Number(poc.decisores),
        motivo: poc.motivo,
      });
      return "Autorização criada e PENDENTE: aprove a configuração do tenant na lista acima para liberar a operação.";
    });
  }

  const pendentes = configs.filter((c) => !c.aprovada);
  const pacotesPendentes = pacotes.filter((p) => !p.aprovado);

  return (
    <Card>
      <SectionLabel>Administração — franquias, pacotes e auditoria (super administrador)</SectionLabel>
      {aviso && <p className="mb-2 rounded-md bg-surf2 p-2 text-[12px] text-muted">{aviso}</p>}

      <h3 className="mb-1 text-[12px] font-semibold">Matriz de franquias por plano</h3>
      <table className="mb-2 w-full border-collapse text-[12px]">
        <tbody>
          {matriz.map((l) => {
            const situacao = SITUACAO_MATRIZ[l.situacao] ?? { rotulo: l.situacao, tom: "muted" as const };
            return (
              <tr key={l.matriz} className="border-b border-border">
                <td className="p-1.5 font-semibold">{l.matriz}</td>
                <td className="p-1.5 text-muted">{l.plano ?? "—"}</td>
                <td className="p-1.5">
                  <Badge tone={situacao.tom}>{situacao.rotulo}</Badge>
                </td>
                <td className="p-1.5">
                  {l.situacao !== "configuravel_por_administrador" && (
                    <Select
                      aria-label={`Plano que recebe a linha ${l.matriz}`}
                      value={mapeamento[l.matriz] ?? ""}
                      onChange={(ev) => setMapeamento({ ...mapeamento, [l.matriz]: ev.target.value })}
                    >
                      <option value="">{l.plano ? "Plano de mesmo nome" : "Escolha o plano..."}</option>
                      {planos.map((p) => (
                        <option key={p.plano_id} value={p.plano_id}>
                          {p.plano}
                        </option>
                      ))}
                    </Select>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <Button size="sm" disabled={ocupado} onClick={aplicarMatriz}>
          Aplicar matriz aprovada
        </Button>
        <span className="text-[11px] text-muted">Idempotente e versionado. Nenhum plano é criado ou adivinhado: ligue cada linha ao plano certo.</span>
      </div>

      <h3 className="mb-1 text-[12px] font-semibold">Configuração por plano ou tenant</h3>
      <div className="mb-2 overflow-x-auto">
        <table className="w-full border-collapse text-[12px]">
          <thead>
            <tr className="border-b border-border text-[9.5px] tracking-wide text-muted uppercase">
              <th className="p-1.5 text-left">Escopo</th>
              <th className="p-1.5 text-left">Versão</th>
              <th className="p-1.5 text-left">Franquia / pesquisa</th>
              <th className="p-1.5 text-left">Decisores máx.</th>
              <th className="p-1.5 text-left">Situação</th>
              <th className="p-1.5" />
            </tr>
          </thead>
          <tbody>
            {configs.slice(0, 20).map((c) => (
              <tr key={c.id} className="border-b border-border">
                <td className="p-1.5">{c.tenant_id ? `tenant ${c.tenant_id}` : `plano ${planos.find((p) => p.plano_id === c.plano_id)?.plano ?? c.plano_id}`}</td>
                <td className="p-1.5 text-muted">v{c.versao}</td>
                <td className="p-1.5 tabular-nums">
                  {c.modo === "poc_autorizada" ? "POC (por autorização)" : `${c.franquia_creditos ?? "—"} / ${c.limite_creditos_pesquisa ?? "—"}`}
                </td>
                <td className="p-1.5 tabular-nums">{c.decisores_por_empresa_max ?? "—"}</td>
                <td className="p-1.5">
                  <Badge tone={c.aprovada ? "green" : "amber"}>{c.aprovada ? "aprovada" : "pendente"}</Badge>
                </td>
                <td className="p-1.5 text-right">
                  {!c.aprovada && (
                    <Button size="sm" variant="ghost" disabled={ocupado || c.faltando.length > 0} onClick={() => executar(async () => { await api.post(`/admin/enriquecimento/config/${c.id}/aprovar`, {}); return "Configuração aprovada (auditada)."; })}>
                      Aprovar
                    </Button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {pendentes.length > 0 && <p className="mt-1 text-[11px] text-amber">{pendentes.length} versão(ões) aguardando aprovação.</p>}
      </div>
      <form onSubmit={salvarConfig} className="mb-3 grid grid-cols-2 gap-2 lg:grid-cols-4">
        <Select aria-label="Escopo da configuração" value={form.alvo} onChange={(ev) => setForm({ ...form, alvo: ev.target.value })}>
          <option value="plano">Plano</option>
          <option value="tenant">Tenant (contrato / Enterprise / POC)</option>
        </Select>
        {form.alvo === "plano" ? (
          <Select aria-label="Plano" value={form.plano_id} onChange={(ev) => setForm({ ...form, plano_id: ev.target.value })}>
            <option value="">Escolha o plano...</option>
            {planos.map((p) => (
              <option key={p.plano_id} value={p.plano_id}>
                {p.plano}
              </option>
            ))}
          </Select>
        ) : (
          <Input aria-label="Tenant" placeholder="id do tenant" value={form.tenant_id} onChange={(ev) => setForm({ ...form, tenant_id: ev.target.value })} />
        )}
        <Select aria-label="Modo" value={form.modo} onChange={(ev) => setForm({ ...form, modo: ev.target.value })}>
          <option value="franquia_fixa">Franquia fixa</option>
          <option value="poc_autorizada">POC autorizada</option>
        </Select>
        <Select aria-label="Periodicidade" value={form.periodicidade} onChange={(ev) => setForm({ ...form, periodicidade: ev.target.value })}>
          <option value="mensal">Mensal</option>
          <option value="unica">Única</option>
        </Select>
        {(
          [
            ["franquia_creditos", "Franquia (créditos)"],
            ["limite_creditos_pesquisa", "Créditos por pesquisa"],
            ["decisores_por_empresa_max", "Decisores/empresa (máx.)"],
            ["decisores_por_empresa_padrao", "Decisores/empresa (padrão, opcional)"],
            ["itens_por_lote_max", "Empresas/pesquisa (opcional)"],
            ["limite_pesquisas_periodo", "Pesquisas/mês (opcional)"],
            ["limite_empresas_periodo", "Empresas/mês (opcional)"],
            ["limite_contatos_periodo", "Contatos/mês (opcional)"],
          ] as const
        ).map(([campo, rotulo]) => (
          <Input key={campo} label={rotulo} type="number" min={0} value={form[campo]} onChange={(ev) => setForm({ ...form, [campo]: ev.target.value })} />
        ))}
        <div className="col-span-2 lg:col-span-3">
          <Input label="Motivo (auditado)" value={form.motivo} onChange={(ev) => setForm({ ...form, motivo: ev.target.value })} />
        </div>
        <div className="flex items-end">
          <Button size="sm" type="submit" disabled={ocupado || form.motivo.trim().length < 3}>
            Criar versão pendente
          </Button>
        </div>
      </form>

      <h3 className="mb-1 text-[12px] font-semibold">Pacotes adicionais e rentabilidade</h3>
      {rentabilidade && (
        <>
          <p className="mb-1 text-[11px] text-muted">
            Custo por crédito do provedor: {rentabilidade.custo_unitario_provedor_brl ? custoCredito(rentabilidade.custo_unitario_provedor_brl) : "indefinido"} ({rentabilidade.origem_custo ?? "sem custo registrado"}).
            {rentabilidade.premissa_fator ? " Relação crédito do cliente × provedor ainda não aprovada: calculado 1:1." : ""} Recalculado a cada leitura.
          </p>
          <table className="mb-2 w-full border-collapse text-[12px]">
            <thead>
              <tr className="border-b border-border text-[9.5px] tracking-wide text-muted uppercase">
                <th className="p-1.5 text-left">Pacote</th>
                <th className="p-1.5 text-right">Preço</th>
                <th className="p-1.5 text-right">Custo</th>
                <th className="p-1.5 text-right">Lucro bruto</th>
                <th className="p-1.5 text-right">Markup</th>
                <th className="p-1.5 text-right">Margem</th>
              </tr>
            </thead>
            <tbody>
              {rentabilidade.pacotes.map((p) => (
                <tr key={p.codigo} className="border-b border-border">
                  <td className="p-1.5">{p.codigo}{p.creditos ? ` · ${p.creditos}` : ""}</td>
                  <td className="p-1.5 text-right tabular-nums">{p.preco_total_brl ? reais(p.preco_total_brl) : "sob negociação"}</td>
                  <td className="p-1.5 text-right tabular-nums">{p.custo_total_brl ? reais(p.custo_total_brl) : "—"}</td>
                  <td className="p-1.5 text-right tabular-nums">{p.lucro_bruto_brl ? reais(p.lucro_bruto_brl) : "—"}</td>
                  <td className="p-1.5 text-right tabular-nums">{p.markup_percentual ? percentual(p.markup_percentual) : "—"}</td>
                  <td className="p-1.5 text-right tabular-nums">{p.margem_bruta_percentual ? percentual(p.margem_bruta_percentual) : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
      {pacotesPendentes.map((p) => (
        <div key={p.id} className="mb-1 flex items-center gap-2 text-[12px]">
          <Badge tone="amber">pendente</Badge>
          <span>{p.codigo} v{p.versao}: {p.creditos ?? "—"} créditos · {reais(p.preco_total_brl)}</span>
          <Button size="sm" variant="ghost" disabled={ocupado} onClick={() => executar(async () => { await api.post(`/admin/enriquecimento/pacotes/${p.id}/aprovar`, {}); return "Pacote aprovado (auditado)."; })}>
            Aprovar
          </Button>
        </div>
      ))}
      <p className="mb-3 text-[11px] text-muted">Pacotes novos ou reajustes são criados pela API administrativa (PUT /admin/enriquecimento/pacotes) e nascem pendentes; o pedido em andamento mantém o preço congelado.</p>

      <h3 className="mb-1 text-[12px] font-semibold">Lote de compra de créditos do provedor</h3>
      <form onSubmit={registrarLote} className="mb-3 flex flex-wrap items-end gap-2">
        <Input label="Referência" value={lote.referencia} onChange={(ev) => setLote({ ...lote, referencia: ev.target.value })} placeholder="ex.: APORTE-LUSHA-2026-11" />
        <Input label="Créditos" type="number" min={1} value={lote.quantidade} onChange={(ev) => setLote({ ...lote, quantidade: ev.target.value })} />
        <Input label="Custo total (R$)" value={lote.custo} onChange={(ev) => setLote({ ...lote, custo: ev.target.value })} placeholder="269,94" />
        <Input label="Data da compra" type="date" value={lote.data} onChange={(ev) => setLote({ ...lote, data: ev.target.value })} />
        <Button size="sm" type="submit" disabled={ocupado || !lote.referencia || !lote.quantidade || !lote.custo}>
          Registrar lote
        </Button>
      </form>

      <h3 className="mb-1 text-[12px] font-semibold">POC: teto calculado e autorização</h3>
      <form onSubmit={calcularTeto} className="mb-1 flex flex-wrap items-end gap-2">
        <Input label="Empresas" type="number" min={1} value={poc.empresas} onChange={(ev) => setPoc({ ...poc, empresas: ev.target.value })} />
        <Input label="Decisores por empresa" type="number" min={1} value={poc.decisores} onChange={(ev) => setPoc({ ...poc, decisores: ev.target.value })} />
        <Button size="sm" type="submit" variant="ghost" disabled={ocupado || !poc.empresas}>
          Calcular teto
        </Button>
        <Input label="Tenant da POC" value={poc.tenant} onChange={(ev) => setPoc({ ...poc, tenant: ev.target.value })} />
        <Input label="Motivo" value={poc.motivo} onChange={(ev) => setPoc({ ...poc, motivo: ev.target.value })} />
        <Button size="sm" type="button" disabled={ocupado || !poc.tenant || !poc.empresas || poc.motivo.trim().length < 3} onClick={autorizarPoc}>
          Autorizar (pendente)
        </Button>
      </form>
      {teto && (
        <p className="mb-3 text-[12px] text-muted">
          Teto: {teto.creditos_cliente_teto} crédito(s) do cliente ({teto.creditos_provedor_teto} do provedor) · custo máximo {reais(teto.custo_maximo_brl)} · venda máxima {reais(teto.valor_venda_maximo_brl)}. {teto.aviso}
        </p>
      )}

      <h3 className="mb-1 text-[12px] font-semibold">Compras de pacotes (todos os tenants)</h3>
      <table className="mb-3 w-full border-collapse text-[12px]">
        <tbody>
          {compras.map((c) => (
            <tr key={c.id} className="border-b border-border">
              <td className="p-1.5 text-muted">{dataCurta(c.criado_em)}</td>
              <td className="p-1.5">{c.tenant_id}</td>
              <td className="p-1.5">{c.pacote} · {c.creditos}</td>
              <td className="p-1.5 text-right tabular-nums">{reais(c.preco_total_brl)}</td>
              <td className="p-1.5"><Badge tone={c.status === "APROVADA" ? "green" : c.status === "PENDENTE" ? "amber" : "red"}>{c.status.toLowerCase()}</Badge></td>
            </tr>
          ))}
          {compras.length === 0 && (
            <tr>
              <td className="p-2 text-center text-muted">Nenhuma compra ainda.</td>
            </tr>
          )}
        </tbody>
      </table>

      <h3 className="mb-1 text-[12px] font-semibold">Auditoria de enriquecimento</h3>
      <div className="max-h-64 overflow-y-auto">
        <table className="w-full border-collapse text-[12px]">
          <tbody>
            {auditoria.map((a) => (
              <tr key={a.id} className="border-b border-border">
                <td className="p-1.5 whitespace-nowrap text-muted">{dataCurta(a.criado_em)}</td>
                <td className="p-1.5">{a.evento.replace("enriquecimento_", "").replaceAll("_", " ")}</td>
                <td className="p-1.5 text-muted">#{a.entidade_id}</td>
                <td className="p-1.5 text-muted">ator {a.ator_id ?? "sistema"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}
