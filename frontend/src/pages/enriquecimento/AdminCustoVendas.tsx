import { useCallback, useEffect, useState, type FormEvent } from "react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, SectionLabel } from "@/components/ui/Card";
import { Input, Select } from "@/components/ui/Input";
import { api, mensagemErro } from "@/lib/api";
import { useAuth } from "@/lib/auth";

import { custoCredito, dataHora, reais } from "./formatos";

interface VersaoCusto {
  id: number;
  versao: number;
  custo_mensal_usd: string;
  creditos_anuais: number;
  creditos_mensais: number;
  cambio_planejamento_brl: string;
  custo_unitario_usd: string;
  custo_unitario_brl: string;
  custo_mensal_brl: string;
  aprovada: boolean;
  vigente: boolean;
}

interface Efetivo {
  configurado: boolean;
  base_do_calculo?: string;
  custo_mensal_planejamento_brl?: string;
  custo_mensal_efetivo_brl?: string | null;
  creditos_referencia_mes?: number;
  creditos_consumidos: number;
  creditos_ociosos?: number;
  ociosidade_percentual?: string;
  custo_efetivo_por_credito_consumido_brl?: string | null;
  aviso?: string | null;
}

interface DadosCusto {
  versoes: VersaoCusto[];
  efetivo_no_mes: Efetivo;
}

interface Venda {
  compra_id: number;
  tenant_id: string;
  pacote: string;
  creditos: number;
  preco_total_brl: string;
  status: string;
  valor_pago_brl: string | null;
  taxa_pagamento_brl: string | null;
  valor_liquido_brl: string | null;
  contestacao_status: string | null;
  nota: { status: string; numero: string | null; erro: string | null; tentativas: number } | null;
  situacao: string;
  situacao_rotulo: string;
  situacao_fiscal: string;
  situacao_fiscal_rotulo: string;
  credito_confere: boolean;
  criado_em: string;
}

interface DadosVendas {
  resumo: {
    por_situacao: Record<string, number>;
    por_situacao_fiscal: Record<string, number>;
    vendas_aprovadas: number;
    bruto_brl: string;
    taxas_informadas_brl: string;
    liquido_informado_brl: string;
    creditos_que_nao_conferem: number[];
  };
  vendas: Venda[];
}

interface Estorno {
  id: number;
  compra_id: number;
  tenant_id: string;
  tipo: string;
  creditos_solicitados: number;
  justificativa: string;
  evidencia: string;
  status: string;
  solicitado_por: string;
  creditos_revertidos: number | null;
  creditos_ja_consumidos: number | null;
}

const TOM_SITUACAO: Record<string, "green" | "amber" | "red" | "muted"> = {
  conciliada: "green", aguardando_pagamento: "muted", pagamento_rejeitado: "muted", divergente: "red", contestada: "red", estornada: "muted",
};
const TOM_FISCAL: Record<string, "green" | "amber" | "red" | "muted"> = { emitida: "green", pendente: "amber", sem_emissor: "amber", falha: "red", nao_aplicavel: "muted" };
const TOM_ESTORNO: Record<string, "green" | "amber" | "red" | "muted"> = { SOLICITADO: "amber", EXECUTADO: "green", REJEITADO: "muted", APROVADO: "amber" };
const CAMPOS_PAGAMENTO_VAZIO = { referencia: "", periodo: "", valor_usd: "", taxa: "", encargos: "", pago_em: "" };

/** Custo contratual do provedor (USD, câmbio de planejamento), validação do contrato, pagamentos efetivos ao provedor, vendas com nota fiscal e conciliação, e
 * estorno MANUAL de créditos. Só o super administrador. Nada aqui é automático: contestações só sinalizam e estorno exige justificativa e aprovação de outra pessoa. */
export function AdminCustoVendas() {
  const { usuario } = useAuth();
  const [custo, setCusto] = useState<DadosCusto | null>(null);
  const [vendas, setVendas] = useState<DadosVendas | null>(null);
  const [estornos, setEstornos] = useState<Estorno[]>([]);
  const [aviso, setAviso] = useState<string | null>(null);
  const [ocupado, setOcupado] = useState(false);
  const [novoCusto, setNovoCusto] = useState({ usd: "", anuais: "", cambio: "", motivo: "" });
  const [pagamento, setPagamento] = useState(CAMPOS_PAGAMENTO_VAZIO);
  const [estornoDe, setEstornoDe] = useState<Venda | null>(null);
  const [pedido, setPedido] = useState({ tipo: "ESTORNO", creditos: "", justificativa: "", evidencia: "" });
  const [motivoDecisao, setMotivoDecisao] = useState("");

  const carregar = useCallback(() => {
    api.get<DadosCusto>("/admin/enriquecimento/custo?provedor=lusha").then(setCusto).catch(() => setCusto(null));
    api.get<DadosVendas>("/admin/enriquecimento/vendas?limite=50").then(setVendas).catch(() => setVendas(null));
    api.get<Estorno[]>("/admin/enriquecimento/estornos").then(setEstornos).catch(() => setEstornos([]));
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

  const vigente = custo?.versoes.find((v) => v.vigente);
  const pendentes = custo?.versoes.filter((v) => !v.aprovada) ?? [];
  const abertos = estornos.filter((e) => e.status === "SOLICITADO");

  function salvarCusto(evento: FormEvent) {
    evento.preventDefault();
    executar(async () => {
      const nova = await api.put<VersaoCusto>("/admin/enriquecimento/custo", {
        custo_mensal_usd: novoCusto.usd, creditos_anuais: Number(novoCusto.anuais), cambio_planejamento_brl: novoCusto.cambio, motivo: novoCusto.motivo,
      });
      setNovoCusto({ usd: "", anuais: "", cambio: "", motivo: "" });
      return `Versão ${nova.versao} criada e PENDENTE de aprovação (custo unitário ${custoCredito(nova.custo_unitario_brl)}). Depois de aprovada, o contrato precisa ser validado de novo.`;
    });
  }

  function sincronizarTarifas() {
    executar(async () => {
      const r = await api.post<{ alterada: boolean; versao: number; tarifas: { busca: number; email: number; telefone: number | null } }>(
        "/admin/enriquecimento/provedores/lusha/sincronizar-politica", {},
      );
      return r.alterada
        ? `Política v${r.versao} publicada a partir das tarifas que a Lusha informa (busca ${r.tarifas.busca}, e-mail ${r.tarifas.email}${r.tarifas.telefone !== null ? `, telefone ${r.tarifas.telefone}` : ""} crédito(s) por unidade).`
        : "A política vigente já corresponde às tarifas informadas pela Lusha.";
    });
  }

  function registrarPagamento(evento: FormEvent) {
    evento.preventDefault();
    executar(async () => {
      await api.post("/admin/enriquecimento/pagamentos-provedor", {
        referencia: pagamento.referencia, periodo: pagamento.periodo, valor_usd: pagamento.valor_usd.replace(",", "."), taxa_cambio_efetiva: pagamento.taxa.replace(",", "."),
        encargos_brl: (pagamento.encargos || "0").replace(",", "."), pago_em: new Date(pagamento.pago_em || Date.now()).toISOString(),
      });
      setPagamento(CAMPOS_PAGAMENTO_VAZIO);
      return "Pagamento ao provedor registrado. O custo efetivo do ciclo passa a usar o valor realmente pago.";
    });
  }

  function solicitarEstorno(evento: FormEvent) {
    evento.preventDefault();
    if (!estornoDe) return;
    executar(async () => {
      await api.post(`/admin/enriquecimento/compras/${estornoDe.compra_id}/estornos`, {
        tipo: pedido.tipo, creditos: Number(pedido.creditos), justificativa: pedido.justificativa, evidencia: pedido.evidencia,
      });
      setEstornoDe(null);
      setPedido({ tipo: "ESTORNO", creditos: "", justificativa: "", evidencia: "" });
      return "Pedido de estorno criado. Nada foi revertido: outro administrador precisa aprovar.";
    });
  }

  const ef = custo?.efetivo_no_mes;
  return (
    <Card>
      <SectionLabel>Custo do provedor, vendas e estornos (super administrador)</SectionLabel>
      {aviso && <p className="mb-2 rounded-md bg-surf2 p-2 text-[12px] text-muted">{aviso}</p>}

      <h3 className="mb-1 text-[12px] font-semibold">Custo contratual e tarifas do provedor</h3>
      {vigente ? (
        <dl className="mb-2 grid grid-cols-2 gap-2 text-[12px] lg:grid-cols-4">
          <Item rotulo="Custo mensal" valor={`USD ${Number(vigente.custo_mensal_usd).toLocaleString("pt-BR")}`} />
          <Item rotulo="Créditos" valor={`${vigente.creditos_anuais.toLocaleString("pt-BR")}/ano · ${vigente.creditos_mensais.toLocaleString("pt-BR")}/mês`} />
          <Item rotulo="Câmbio de planejamento" valor={reais(vigente.cambio_planejamento_brl)} />
          <Item rotulo="Custo nominal por crédito" valor={custoCredito(vigente.custo_unitario_brl)} />
          <Item rotulo="Custo mensal (planejamento)" valor={reais(vigente.custo_mensal_brl)} />
          <Item rotulo="Versão" valor={`v${vigente.versao}`} />
        </dl>
      ) : (
        <p className="mb-2 text-[12px] text-amber">Nenhum custo contratual cadastrado: a pesquisa Lusha permanece bloqueada.</p>
      )}
      {ef?.configurado && (
        <p className="mb-2 text-[12px] text-muted">
          Neste mês: {ef.creditos_consumidos.toLocaleString("pt-BR")} de {ef.creditos_referencia_mes?.toLocaleString("pt-BR")} créditos consumidos ({ef.creditos_ociosos?.toLocaleString("pt-BR")} ociosos,{" "}
          {ef.ociosidade_percentual?.replace(".", ",")}%). Custo efetivo por crédito consumido:{" "}
          <strong className="text-text">{ef.custo_efetivo_por_credito_consumido_brl ? custoCredito(ef.custo_efetivo_por_credito_consumido_brl) : "— (sem consumo)"}</strong> sobre{" "}
          {ef.base_do_calculo === "pagamentos_efetivos" ? `os pagamentos efetivos (${reais(ef.custo_mensal_efetivo_brl ?? null)})` : `o custo de planejamento (${reais(ef.custo_mensal_planejamento_brl ?? null)})`}.
          {ef.aviso ? ` ${ef.aviso}` : ""}
        </p>
      )}
      {pendentes.map((v) => (
        <div key={v.id} className="mb-1 flex items-center gap-2 text-[12px]">
          <Badge tone="amber">pendente</Badge>
          <span>
            v{v.versao}: USD {v.custo_mensal_usd}, {v.creditos_anuais} créditos/ano, câmbio {v.cambio_planejamento_brl}
          </span>
          <Button size="sm" variant="ghost" disabled={ocupado} onClick={() => executar(async () => { await api.post(`/admin/enriquecimento/custo/${v.id}/aprovar`, {}); return "Custo aprovado (auditado)."; })}>
            Aprovar
          </Button>
        </div>
      ))}
      <div className="mb-3 flex flex-wrap items-center gap-2 text-[12px]">
        <Button size="sm" variant="ghost" disabled={ocupado} onClick={sincronizarTarifas}>
          Sincronizar tarifas com a Lusha
        </Button>
        <span className="text-muted">
          Lê as tarifas por ação que a própria Lusha informa (busca, e-mail, telefone) e publica a política. Roda sozinha no agendador; sem a tarifa da busca ou do e-mail o
          motivo técnico aparece aqui.
        </span>
      </div>
      <form onSubmit={salvarCusto} className="mb-3 flex flex-wrap items-end gap-2">
        <Input label="Custo mensal (USD)" value={novoCusto.usd} onChange={(ev) => setNovoCusto({ ...novoCusto, usd: ev.target.value })} placeholder="600" />
        <Input label="Créditos por ano" type="number" min={12} value={novoCusto.anuais} onChange={(ev) => setNovoCusto({ ...novoCusto, anuais: ev.target.value })} placeholder="81600" />
        <Input label="Câmbio de planejamento (R$/USD)" value={novoCusto.cambio} onChange={(ev) => setNovoCusto({ ...novoCusto, cambio: ev.target.value })} placeholder="6.00" />
        <Input label="Motivo (auditado)" value={novoCusto.motivo} onChange={(ev) => setNovoCusto({ ...novoCusto, motivo: ev.target.value })} />
        <Button size="sm" type="submit" variant="ghost" disabled={ocupado || !novoCusto.usd || !novoCusto.anuais || !novoCusto.cambio || novoCusto.motivo.trim().length < 3}>
          Criar versão pendente
        </Button>
      </form>

      <h3 className="mb-1 text-[12px] font-semibold">Pagamento efetivo ao provedor (conciliação financeira)</h3>
      <p className="mb-1 text-[11px] text-muted">Informe o USD pago, a taxa de câmbio EFETIVAMENTE aplicada e os encargos efetivamente cobrados. O câmbio de planejamento não é o valor contábil.</p>
      <form onSubmit={registrarPagamento} className="mb-3 flex flex-wrap items-end gap-2">
        <Input label="Referência (fatura)" value={pagamento.referencia} onChange={(ev) => setPagamento({ ...pagamento, referencia: ev.target.value })} />
        <Input label="Ciclo (AAAA-MM)" value={pagamento.periodo} onChange={(ev) => setPagamento({ ...pagamento, periodo: ev.target.value })} placeholder="2026-10" />
        <Input label="Valor (USD)" value={pagamento.valor_usd} onChange={(ev) => setPagamento({ ...pagamento, valor_usd: ev.target.value })} />
        <Input label="Taxa de câmbio efetiva" value={pagamento.taxa} onChange={(ev) => setPagamento({ ...pagamento, taxa: ev.target.value })} />
        <Input label="Encargos (R$)" value={pagamento.encargos} onChange={(ev) => setPagamento({ ...pagamento, encargos: ev.target.value })} placeholder="0" />
        <Input label="Data do pagamento" type="date" value={pagamento.pago_em} onChange={(ev) => setPagamento({ ...pagamento, pago_em: ev.target.value })} />
        <Button size="sm" type="submit" disabled={ocupado || !pagamento.referencia || !pagamento.periodo || !pagamento.valor_usd || !pagamento.taxa}>
          Registrar pagamento
        </Button>
      </form>

      <h3 className="mb-1 text-[12px] font-semibold">Vendas, nota fiscal e conciliação</h3>
      {vendas && (
        <>
          <p className="mb-1 text-[12px] text-muted">
            {vendas.resumo.vendas_aprovadas} venda(s) aprovada(s): bruto {reais(vendas.resumo.bruto_brl)} · tarifas informadas pelo provedor de pagamento {reais(vendas.resumo.taxas_informadas_brl)} · líquido
            informado {reais(vendas.resumo.liquido_informado_brl)}.
            {vendas.resumo.creditos_que_nao_conferem.length > 0 && (
              <span className="text-red"> Atenção: o crédito lançado no razão não confere com o pedido nas compras {vendas.resumo.creditos_que_nao_conferem.join(", ")}.</span>
            )}
          </p>
          <div className="mb-3 max-h-72 overflow-auto">
            <table className="w-full border-collapse text-[12px]">
              <tbody>
                {vendas.vendas.map((v) => (
                  <tr key={v.compra_id} className="border-b border-border">
                    <td className="p-1.5 whitespace-nowrap text-muted">{dataHora(v.criado_em)}</td>
                    <td className="p-1.5">{v.tenant_id}</td>
                    <td className="p-1.5">{v.pacote} · {v.creditos}</td>
                    <td className="p-1.5 text-right tabular-nums">{reais(v.preco_total_brl)}</td>
                    <td className="p-1.5">
                      <Badge tone={TOM_SITUACAO[v.situacao] ?? "muted"}>{v.situacao_rotulo}</Badge>
                    </td>
                    <td className="p-1.5">
                      <Badge tone={TOM_FISCAL[v.situacao_fiscal] ?? "muted"}>{v.nota?.status === "EMITIDA" ? `NF ${v.nota.numero}` : v.situacao_fiscal_rotulo}</Badge>
                      {v.nota?.erro ? <span className="ml-1 text-muted">({v.nota.erro})</span> : null}
                    </td>
                    <td className="p-1.5 text-right whitespace-nowrap">
                      {(v.situacao_fiscal === "sem_emissor" || v.situacao_fiscal === "falha" || v.situacao_fiscal === "pendente") && (
                        <Button size="sm" variant="ghost" disabled={ocupado} onClick={() => executar(async () => { const r = await api.post<{ status: string; erro: string | null }>(`/admin/enriquecimento/compras/${v.compra_id}/emitir-nota`, {}); return r.status === "EMITIDA" ? "Nota emitida." : r.status === "SEM_EMISSOR" ? "Nenhum emissor fiscal está configurado neste ambiente: a nota continua a emitir." : `A nota não foi emitida: ${r.erro ?? "sem detalhe"}.`; })}>
                          Emitir nota
                        </Button>
                      )}
                      {v.status === "APROVADA" && v.situacao !== "estornada" && (
                        <Button size="sm" variant="ghost" disabled={ocupado} onClick={() => { setEstornoDe(v); setPedido({ ...pedido, creditos: String(v.creditos) }); }}>
                          Estornar...
                        </Button>
                      )}
                    </td>
                  </tr>
                ))}
                {vendas.vendas.length === 0 && (
                  <tr>
                    <td className="p-2 text-center text-muted">Nenhuma venda ainda.</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </>
      )}

      {estornoDe && (
        <form onSubmit={solicitarEstorno} className="mb-3 rounded-md bg-surf2 p-2.5">
          <p className="mb-1 text-[12px] font-semibold">Pedido manual de estorno: compra #{estornoDe.compra_id} ({estornoDe.pacote}, {estornoDe.creditos} créditos)</p>
          <p className="mb-2 text-[11px] text-muted">
            Só reverte créditos adicionais ainda não consumidos nem vencidos, por lançamento compensatório. O dinheiro é devolvido fora da plataforma. Outro administrador precisa aprovar.
          </p>
          <div className="flex flex-wrap items-end gap-2">
            <Select aria-label="Tipo" value={pedido.tipo} onChange={(ev) => setPedido({ ...pedido, tipo: ev.target.value })}>
              <option value="ESTORNO">Estorno</option>
              <option value="CHARGEBACK">Chargeback</option>
              <option value="CANCELAMENTO">Cancelamento</option>
              <option value="AJUSTE">Ajuste</option>
            </Select>
            <Input label="Créditos" type="number" min={1} max={estornoDe.creditos} value={pedido.creditos} onChange={(ev) => setPedido({ ...pedido, creditos: ev.target.value })} />
            <div className="min-w-64 flex-1">
              <Input label="Justificativa" value={pedido.justificativa} onChange={(ev) => setPedido({ ...pedido, justificativa: ev.target.value })} />
            </div>
            <Input label="Evidência (protocolo, contestação)" value={pedido.evidencia} onChange={(ev) => setPedido({ ...pedido, evidencia: ev.target.value })} />
            <Button size="sm" type="submit" disabled={ocupado || !pedido.creditos || pedido.justificativa.trim().length < 10 || pedido.evidencia.trim().length < 5}>
              Solicitar
            </Button>
            <Button size="sm" type="button" variant="ghost" onClick={() => setEstornoDe(null)}>
              Cancelar
            </Button>
          </div>
        </form>
      )}

      <h3 className="mb-1 text-[12px] font-semibold">Pedidos de estorno</h3>
      {abertos.length > 0 && (
        <div className="mb-1 flex items-center gap-2">
          <Input aria-label="Motivo da decisão" placeholder="Motivo da decisão (obrigatório)" value={motivoDecisao} onChange={(ev) => setMotivoDecisao(ev.target.value)} />
        </div>
      )}
      <table className="mb-1 w-full border-collapse text-[12px]">
        <tbody>
          {estornos.map((e) => (
            <tr key={e.id} className="border-b border-border">
              <td className="p-1.5">#{e.id} · compra {e.compra_id}</td>
              <td className="p-1.5">{e.tipo.toLowerCase()} · {e.creditos_solicitados}</td>
              <td className="p-1.5 text-muted">{e.justificativa}</td>
              <td className="p-1.5">
                <Badge tone={TOM_ESTORNO[e.status] ?? "muted"}>{e.status.toLowerCase()}</Badge>
                {e.status === "EXECUTADO" && <span className="ml-1 text-muted">{e.creditos_revertidos} revertidos · {e.creditos_ja_consumidos} já consumidos</span>}
              </td>
              <td className="p-1.5 text-right whitespace-nowrap">
                {e.status === "SOLICITADO" && (
                  <>
                    <Button size="sm" variant="ghost" disabled={ocupado || motivoDecisao.trim().length < 5 || e.solicitado_por === String(usuario?.id)} onClick={() => executar(async () => { await api.post(`/admin/enriquecimento/estornos/${e.id}/decidir`, { aprovar: true, motivo: motivoDecisao }); setMotivoDecisao(""); return "Estorno aprovado e executado (lançamento compensatório no razão)."; })}>
                      Aprovar
                    </Button>
                    <Button size="sm" variant="ghost" disabled={ocupado || motivoDecisao.trim().length < 5} onClick={() => executar(async () => { await api.post(`/admin/enriquecimento/estornos/${e.id}/decidir`, { aprovar: false, motivo: motivoDecisao }); setMotivoDecisao(""); return "Pedido rejeitado."; })}>
                      Rejeitar
                    </Button>
                  </>
                )}
              </td>
            </tr>
          ))}
          {estornos.length === 0 && (
            <tr>
              <td className="p-2 text-center text-muted">Nenhum pedido de estorno.</td>
            </tr>
          )}
        </tbody>
      </table>
      <p className="text-[11px] text-muted">Quem solicita um estorno não pode aprová-lo. Avisos de reembolso ou chargeback do provedor de pagamento apenas marcam a venda como contestada.</p>
    </Card>
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
