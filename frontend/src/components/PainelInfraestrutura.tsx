import { useCallback, useEffect, useState, type FormEvent } from "react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, SectionLabel } from "@/components/ui/Card";
import { Input, Select } from "@/components/ui/Input";
import { brl } from "@/lib/aiCredits";
import { api, mensagemErro } from "@/lib/api";
import type { Infraestrutura } from "@/lib/comissoes";

const TOM_STATUS: Record<string, "green" | "cyan" | "amber" | "red"> = {
  NORMAL: "green",
  ATTENTION: "cyan",
  REVIEW: "amber",
  CRITICAL: "red",
  CAPACITY_REACHED: "red",
};

const pct = (v: number | null | undefined) =>
  v === null || v === undefined
    ? "—"
    : `${(v * 100).toLocaleString("pt-BR", { maximumFractionDigits: 1 })}%`;
const valor = (v: number | null | undefined) =>
  v === null || v === undefined ? "—" : brl(v);
const numero = (form: FormData, campo: string) => {
  const texto = String(form.get(campo) ?? "")
    .trim()
    .replace(",", ".");
  return texto ? Number(texto) : null;
};

/** Admin → Parâmetros financeiros → Infraestrutura (D-076): Infrastructure Cost Pool com custo real e provisionado
 * (plano máximo), Provider Economics, capacidade, alertas (decisão humana), projeção e política de pesos/limiares.
 * Nenhum fornecedor ou valor vem pronto. */
export function PainelInfraestrutura({
  onAlterado,
}: {
  onAlterado: (mensagem: string) => void;
}) {
  const [dados, setDados] = useState<Infraestrutura | null>(null);

  const carregar = useCallback(async () => {
    try {
      setDados(await api.get<Infraestrutura>("/comissoes/infraestrutura"));
    } catch (error) {
      onAlterado(
        mensagemErro(error, "Não foi possível carregar a infraestrutura."),
      );
    }
  }, [onAlterado]);

  useEffect(() => {
    carregar();
  }, [carregar]);

  async function enviar(
    evento: FormEvent<HTMLFormElement>,
    rota: string,
    corpo: (f: FormData) => object,
    metodo: "post" | "patch" = "post",
  ) {
    evento.preventDefault();
    const formulario = evento.currentTarget;
    try {
      const resposta = await api[metodo]<{ aguardando_calculadas?: number }>(
        rota,
        corpo(new FormData(formulario)),
      );
      onAlterado(
        `Salvo. ${resposta.aguardando_calculadas ?? 0} recebimento(s) que aguardavam foram calculados.`,
      );
      formulario.reset();
      carregar();
    } catch (error) {
      onAlterado(mensagemErro(error, "Não foi possível salvar."));
    }
  }

  const resumo = dados?.economia.resumo;
  const projecao = dados?.economia.projecao;
  return (
    <Card data-testid="painel-infraestrutura">
      <SectionLabel>
        Infraestrutura — Infrastructure Cost Pool (plano máximo)
      </SectionLabel>
      <div className="mb-2 text-[11px] text-muted">
        A comissão usa o custo PROVISIONADO (plano de referência integral, mesmo
        com uso baixo), alocado por unidades ponderadas (peso do tier × tenants
        ativos) e pelos custos diretos medidos. O custo real fica ao lado para
        FinOps e MAP. Custos já contados como IA/dados no FinOps não entram de
        novo.
      </div>
      {resumo && (
        <div
          className="mb-2 flex flex-wrap gap-3 text-[12px]"
          data-testid="resumo-pool"
        >
          <span>
            Provisionado/mês: <b>{valor(resumo.pool_provisionado_mensal)}</b>
          </span>
          <span>Real/mês: {valor(resumo.pool_real_mensal)}</span>
          <span>Reserva/mês: {valor(resumo.reserva_mensal)}</span>
          <span>
            Infra: {valor(resumo.por_pool.INFRASTRUCTURE)} · Provedores de
            dados: {valor(resumo.por_pool.DATA_PROVIDER)}
          </span>
          <span data-testid="capacidade-nao-alocada">
            Capacidade não alocada/mês:{" "}
            {valor(resumo.capacidade_nao_alocada_mensal)}
          </span>
          <span>Unidades ponderadas: {resumo.unidades_ponderadas}</span>
          <span>Custo ÷ MRR: {pct(resumo.custo_sobre_receita)}</span>
          {resumo.dependencia_maior_fornecedor && (
            <span>
              Maior fornecedor: {resumo.dependencia_maior_fornecedor.fornecedor}{" "}
              ({pct(resumo.dependencia_maior_fornecedor.participacao)})
            </span>
          )}
        </div>
      )}
      {dados && dados.componentes.length === 0 && (
        <Badge tone="amber">
          Nenhum fornecedor cadastrado — comissões em
          AWAITING_INFRASTRUCTURE_COST
        </Badge>
      )}
      {(dados?.economia.alertas_abertos ?? []).map((alerta) => (
        <form
          key={alerta.id}
          className="mt-1.5 flex flex-wrap items-center gap-2 rounded-md border border-border p-2 text-[12px]"
          data-testid="alerta-capacidade"
          onSubmit={(e) =>
            enviar(
              e,
              `/comissoes/infraestrutura/alertas/${alerta.id}/decisao`,
              (f) => ({
                decisao: String(f.get("decisao")),
              }),
            )
          }
        >
          <Badge tone={TOM_STATUS[alerta.nivel] ?? "amber"}>
            {alerta.nivel}
          </Badge>
          <span>
            {alerta.mensagem} ({pct(alerta.utilizacao)})
          </span>
          <Input
            name="decisao"
            required
            placeholder="Decisão tomada (nada é contratado automaticamente)"
            className="flex-1"
          />
          <Button type="submit" size="sm" variant="ghost">
            Registrar decisão
          </Button>
        </form>
      ))}
      <div className="mt-2 overflow-x-auto">
        <table className="w-full border-collapse text-[11.5px]">
          <thead>
            <tr className="border-b border-border text-[9.5px] tracking-wide text-muted uppercase">
              {[
                "Fornecedor",
                "Plano atual → referência",
                "Contratado",
                "Real",
                "Provisionado/mês",
                "Capacidade · uso",
                "Utilização",
                "Por tenant",
                "Por unidade",
                "Custo ÷ receita",
                "Esgotamento",
                "Status",
                "Uso medido",
              ].map((t) => (
                <th key={t} className="p-2 text-left">
                  {t}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {(dados?.economia.componentes ?? []).map((l) => (
              <tr
                key={l.id}
                className="border-b border-border"
                data-testid="linha-fornecedor"
              >
                <td className="p-2 font-semibold">
                  {l.fornecedor}
                  <div className="font-normal text-muted">
                    {l.servico} · {l.categoria} · {l.contabilizacao}
                  </div>
                  <div className="font-normal">
                    <Badge tone={l.no_pool_comissao ? "green" : "muted"}>
                      {l.status_arquitetura}
                    </Badge>{" "}
                    <span className="text-muted">
                      {l.modelo_preco} · {l.tipo_fonte}
                      {l.verificado_em
                        ? ` · verificado ${l.verificado_em}`
                        : ""}
                      {l.revisao_vencida ? " · revisão vencida" : ""}
                    </span>
                  </div>
                  {l.modelo_preco === "USAGE_BASED" && (
                    <div className="font-normal text-muted">
                      {l.envelope
                        ? `Envelope: ${l.envelope.custo_mensal_estimado ?? "—"} ${l.envelope.moeda}/mês`
                        : "Sem capacity envelope"}
                    </div>
                  )}
                </td>
                <td className="p-2">
                  {l.plano_atual ?? "—"} → {l.plano_referencia ?? "—"}
                </td>
                <td className="p-2">
                  {l.custo_contratado ?? "—"} {l.moeda}
                </td>
                <td className="p-2">
                  {l.custo_real ?? "—"} {l.moeda}
                </td>
                <td className="p-2">
                  {valor(l.custo_provisionado_mensal_brl)}
                </td>
                <td className="p-2">
                  {l.capacidade ?? "—"} · {l.uso ?? "—"} {l.unidade_uso ?? ""}
                </td>
                <td className="p-2">{pct(l.utilizacao)}</td>
                <td className="p-2">{valor(l.custo_por_tenant)}</td>
                <td className="p-2">{valor(l.custo_por_unidade_ponderada)}</td>
                <td className="p-2">{pct(l.custo_sobre_receita)}</td>
                <td className="p-2">
                  {l.projecao.esgotamento_estimado ?? "—"}
                </td>
                <td className="p-2">
                  {l.status ? (
                    <Badge tone={TOM_STATUS[l.status] ?? "cyan"}>
                      {l.status}
                    </Badge>
                  ) : (
                    "—"
                  )}
                </td>
                <td className="p-2">
                  <form
                    className="flex gap-1"
                    onSubmit={(e) =>
                      enviar(
                        e,
                        `/comissoes/infraestrutura/componentes/${l.id}/uso`,
                        (f) => ({
                          uso: numero(f, "uso"),
                          fonte: "admin",
                        }),
                      )
                    }
                  >
                    <Input
                      name="uso"
                      required
                      className="w-20"
                      placeholder="uso"
                    />
                    <Button type="submit" size="sm" variant="ghost">
                      OK
                    </Button>
                  </form>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {projecao && (
        <div
          className="mt-2 text-[11px] text-muted"
          data-testid="projecao-infra"
        >
          Projeção {projecao.horizonte_dias} dias: custo provisionado{" "}
          {valor(projecao.custo_infra_projetado_mensal)}/mês; receita recorrente{" "}
          {valor(projecao.receita_recorrente_projetada_mensal)}/mês; custo ÷
          receita {pct(projecao.custo_sobre_receita_projetado)}.{" "}
          {projecao.esgotamentos_ate_180_dias.length
            ? `Esgotamento previsto: ${projecao.esgotamentos_ate_180_dias
                .map((e) => `${e.fornecedor} (${e.data})`)
                .join(", ")} — custo seguinte depende de decisão.`
            : "Nenhum esgotamento previsto em 180 dias."}
        </div>
      )}

      <form
        className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-4"
        data-testid="form-componente-infra"
        onSubmit={(e) =>
          enviar(e, "/comissoes/infraestrutura/componentes", (f) => ({
            fornecedor: String(f.get("fornecedor")),
            servico: String(f.get("servico")),
            categoria: String(f.get("categoria")),
            plano: String(f.get("plano") ?? "") || null,
            plano_referencia: String(f.get("plano_referencia") ?? "") || null,
            ciclo_cobranca: String(f.get("ciclo_cobranca")),
            moeda: String(f.get("moeda") || "BRL"),
            custo_contratado: numero(f, "custo_contratado"),
            custo_referencia: numero(f, "custo_referencia"),
            custo_real: numero(f, "custo_real"),
            capacidade_contratada: numero(f, "capacidade_contratada"),
            uso_atual: numero(f, "uso_atual"),
            unidade_uso: String(f.get("unidade_uso") ?? "") || null,
            politica_custo: String(f.get("politica_custo")),
            metodo_alocacao: String(f.get("metodo_alocacao")),
            contabilizacao: String(f.get("contabilizacao")),
            modelo_preco: String(f.get("modelo_preco")),
            status_arquitetura: String(f.get("status_arquitetura")),
            provisionado_para_comissao:
              String(f.get("status_arquitetura")) !== "AVAILABLE_NOT_ALLOCATED",
            tipo_fonte: String(f.get("tipo_fonte")),
            url_fonte: String(f.get("url_fonte") ?? "") || null,
            verificado_em: String(f.get("verificado_em") ?? "") || null,
            funcao_arquitetural:
              String(f.get("funcao_arquitetural") ?? "") || null,
            vigente_de: String(f.get("vigente_de")),
          }))
        }
      >
        <Input
          name="fornecedor"
          required
          placeholder="Fornecedor (ex.: Render)"
        />
        <Input name="servico" required placeholder="Serviço" />
        <Select name="categoria">
          {(dados?.categorias ?? []).map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </Select>
        <Input name="vigente_de" type="date" required />
        <Input name="plano" placeholder="Plano atual" />
        <Input name="plano_referencia" placeholder="Plano máximo/referência" />
        <Select name="ciclo_cobranca">
          {(dados?.ciclos ?? ["MONTHLY"]).map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </Select>
        <Input name="moeda" placeholder="Moeda (BRL, USD)" defaultValue="BRL" />
        <Input
          name="custo_referencia"
          placeholder="Custo do plano de referência"
        />
        <Input name="custo_contratado" placeholder="Custo do plano atual" />
        <Input name="custo_real" placeholder="Custo real do ciclo" />
        <Input
          name="capacidade_contratada"
          placeholder="Capacidade contratada"
        />
        <Input name="uso_atual" placeholder="Uso atual" />
        <Input name="unidade_uso" placeholder="Unidade (GB, req, créditos)" />
        <Select name="politica_custo">
          <option value="MAX_CONTRACTED_PLAN">
            Plano máximo (conservador)
          </option>
          <option value="ACTUAL_COST">Custo real</option>
        </Select>
        <Select name="metodo_alocacao">
          <option value="WEIGHTED">Alocação ponderada</option>
          <option value="DIRECT">Atribuição direta</option>
        </Select>
        <Select name="contabilizacao">
          <option value="INFRASTRUCTURE">Infraestrutura</option>
          <option value="DATA_PROVIDER">Provedor de dados</option>
          <option value="AI_COST">Já no custo de IA (FinOps)</option>
        </Select>
        <Select name="modelo_preco">
          {(dados?.modelos_preco ?? ["FIXED_PLAN"]).map((m) => (
            <option key={m} value={m}>
              {m}
            </option>
          ))}
        </Select>
        <Select name="status_arquitetura">
          {(dados?.status_arquitetura ?? ["APPLICABLE"]).map((m) => (
            <option key={m} value={m}>
              {m}
            </option>
          ))}
        </Select>
        <Select name="tipo_fonte">
          {(dados?.tipos_fonte ?? ["MANUAL_APPROVED"]).map((m) => (
            <option key={m} value={m}>
              {m}
            </option>
          ))}
        </Select>
        <Input name="url_fonte" placeholder="URL da fonte do preço" />
        <Input name="verificado_em" type="date" title="Verificado em" />
        <Input
          name="funcao_arquitetural"
          placeholder="Função (ex.: PRIMARY_DATABASE)"
        />
        <Button type="submit" size="sm" className="sm:col-span-3">
          Cadastrar fornecedor/plano
        </Button>
      </form>

      <form
        className="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-6"
        onSubmit={(e) =>
          enviar(e, "/comissoes/infraestrutura/custos-diretos", (f) => ({
            componente_id: Number(f.get("componente_id")),
            tenant_id: String(f.get("tenant_id")),
            competencia: String(f.get("competencia")),
            custo: numero(f, "custo"),
            quantidade: numero(f, "quantidade"),
            fonte: "admin",
          }))
        }
      >
        <Select name="componente_id">
          {(dados?.componentes ?? [])
            .filter((c) => c.metodo_alocacao === "DIRECT")
            .map((c) => (
              <option key={c.id} value={c.id}>
                {c.fornecedor} · {c.servico}
              </option>
            ))}
        </Select>
        <Input name="tenant_id" required placeholder="Tenant" />
        <Input name="competencia" required placeholder="AAAA-MM" />
        <Input name="custo" required placeholder="Custo medido" />
        <Input name="quantidade" placeholder="Quantidade" />
        <Button type="submit" size="sm" variant="ghost">
          Custo direto
        </Button>
      </form>

      <form
        className="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-5"
        data-testid="form-envelope"
        onSubmit={(e) => {
          const f = new FormData(e.currentTarget);
          enviar(
            e,
            `/comissoes/infraestrutura/componentes/${String(f.get("componente_id"))}/envelopes`,
            (form) => ({
              horas_computo_provisionadas: numero(form, "horas"),
              armazenamento_gb_provisionado: numero(form, "gb"),
              fonte: String(form.get("fonte") ?? "") || null,
            }),
          );
        }}
      >
        <Select name="componente_id">
          {(dados?.componentes ?? [])
            .filter((c) => c.modelo_preco === "USAGE_BASED")
            .map((c) => (
              <option key={c.id} value={c.id}>
                {c.fornecedor} · {c.servico}
              </option>
            ))}
        </Select>
        <Input
          name="horas"
          required
          placeholder="Horas de computação/mês (CU-h)"
        />
        <Input
          name="gb"
          required
          placeholder="Armazenamento provisionado (GB)"
        />
        <Input name="fonte" placeholder="Decisão/fonte" />
        <Button type="submit" size="sm" variant="ghost">
          Definir capacity envelope
        </Button>
      </form>

      {dados && (
        <form
          className="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-5"
          data-testid="form-politica-infra"
          onSubmit={(e) =>
            enviar(e, "/comissoes/politica-infraestrutura", (f) => ({
              pesos: Object.fromEntries(
                Object.keys(dados.politica.pesos).map((t) => [
                  t,
                  numero(f, `peso_${t}`),
                ]),
              ),
              limiares: Object.fromEntries(
                Object.keys(dados.politica.limiares).map((n) => [
                  n,
                  (numero(f, `lim_${n}`) ?? 0) / 100,
                ]),
              ),
              custo_comissao: String(f.get("custo_comissao")),
              motivo: String(f.get("motivo")),
            }))
          }
        >
          {Object.entries(dados.politica.pesos).map(([tier, peso]) => (
            <label key={tier} className="text-[11px] text-muted">
              Peso {tier}
              <Input name={`peso_${tier}`} defaultValue={String(peso)} />
            </label>
          ))}
          <label className="text-[11px] text-muted">
            Base da comissão
            <Select
              name="custo_comissao"
              defaultValue={dados.politica.custo_comissao}
            >
              <option value="PROVISIONED">Provisionado</option>
              <option value="ACTUAL">Real</option>
            </Select>
          </label>
          {Object.entries(dados.politica.limiares).map(([nivel, limite]) => (
            <label key={nivel} className="text-[11px] text-muted">
              {nivel} (%)
              <Input
                name={`lim_${nivel}`}
                defaultValue={String(Math.round(limite * 100))}
              />
            </label>
          ))}
          <Input
            name="motivo"
            required
            placeholder="Motivo da nova política (auditoria)"
            className="sm:col-span-4"
          />
          <Button type="submit" size="sm" variant="ghost">
            Nova versão
          </Button>
        </form>
      )}
    </Card>
  );
}
