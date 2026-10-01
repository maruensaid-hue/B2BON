import { useCallback, useEffect, useState, type FormEvent } from "react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, SectionLabel } from "@/components/ui/Card";
import { Input, Select } from "@/components/ui/Input";
import { PainelInfraestrutura } from "@/components/PainelInfraestrutura";
import { AcessoRestrito } from "@/pages/admin/AcessoRestrito";
import { brl } from "@/lib/aiCredits";
import { api, mensagemErro } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import {
  descreverTributo,
  pct,
  type Parametros,
  type Waterfall,
} from "@/lib/comissoes";

const AGRUPAR = [
  ["tenant", "Tenant"],
  ["representante", "Representante"],
  ["produto", "Produto"],
  ["venda", "Venda"],
  ["periodo", "Período"],
] as const;

/** Lista JSON de componentes (tributos ou custos); erro de digitação vira mensagem, não tela quebrada. */
function lerJson(texto: string): Record<string, unknown>[] {
  const valor: unknown = JSON.parse(texto);
  if (!Array.isArray(valor)) throw new Error("Informe uma lista JSON.");
  return valor as Record<string, unknown>[];
}

/** Parâmetros financeiros do Commission Engine (D-074, D-075): Tax Profile por tributo, Infrastructure Cost Model,
 * câmbio, Commission Policy e waterfall. Nenhum valor vem pronto: o PO informa, com vigência e fonte; o histórico só muda
 * por recálculo explícito. */
export function ParametrosFinanceiros() {
  const { usuario } = useAuth();
  const [dados, setDados] = useState<Parametros | null>(null);
  const [waterfall, setWaterfall] = useState<Waterfall | null>(null);
  const [agrupar, setAgrupar] = useState("tenant");
  const [mensagem, setMensagem] = useState<string | null>(null);
  const [tributosJson, setTributosJson] = useState("");
  const isSuperAdmin = usuario?.papel === "super_admin";

  const carregar = useCallback(async () => {
    try {
      const [p, w] = await Promise.all([
        api.get<Parametros>("/comissoes/parametros"),
        api.get<Waterfall>(`/comissoes/waterfall?agrupar=${agrupar}`),
      ]);
      setDados(p);
      setWaterfall(w);
    } catch (error) {
      setMensagem(
        mensagemErro(error, "Não foi possível carregar os parâmetros."),
      );
    }
  }, [agrupar]);

  useEffect(() => {
    if (isSuperAdmin) carregar();
  }, [isSuperAdmin, carregar]);

  async function enviar(
    evento: FormEvent<HTMLFormElement>,
    rota: string,
    corpo: (f: FormData) => object,
  ) {
    evento.preventDefault();
    const formulario = evento.currentTarget;
    try {
      const dadosEnvio = corpo(new FormData(formulario));
      const resposta = await api.post<{
        aguardando_calculadas?: number;
        alteradas?: number;
      }>(rota, dadosEnvio);
      setMensagem(
        `Salvo. ${resposta.aguardando_calculadas ?? 0} recebimento(s) que aguardavam foram calculados` +
          (resposta.alteradas !== undefined
            ? `; ${resposta.alteradas} apuração(ões) recalculada(s).`
            : "."),
      );
      formulario.reset();
      carregar();
    } catch (error) {
      setMensagem(mensagemErro(error, "Não foi possível salvar."));
    }
  }

  if (!isSuperAdmin) return <AcessoRestrito />;

  return (
    <div
      className="flex flex-col gap-4 p-5.5"
      data-testid="parametros-financeiros"
    >
      <div>
        <div className="font-head text-xl font-bold">
          Admin — Parâmetros financeiros
        </div>
        <div className="mt-0.5 text-[11px] text-muted">
          Comissão = Margem Comissionável Líquida (receita recebida − impostos
          atribuíveis − infraestrutura provisionada atribuível) × taxa. Sem Tax
          Profile ou sem valores no Infrastructure Cost Pool, a comissão fica
          aguardando e não é paga.
        </div>
      </div>
      {mensagem && <div className="text-[12px] text-muted">{mensagem}</div>}

      <Card data-testid="parametros-pendentes">
        <SectionLabel>
          O que falta para as comissões saírem de AWAITING
        </SectionLabel>
        {dados && dados.pendentes.length === 0 ? (
          <Badge tone="green">Todos os parâmetros informados</Badge>
        ) : (
          <ul className="list-disc pl-5 text-[12px] text-muted">
            {(dados?.pendentes ?? []).map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        )}
      </Card>

      <Card>
        <SectionLabel>
          Tax Profile (Tax Engine, um componente por tributo)
        </SectionLabel>
        <div className="mb-1.5 text-[11px] text-muted">
          IRPJ e CSLL: receita × presunção do tipo de receita × alíquota. ISS
          por município e código de serviço. CBS/IBS-teste não somam à carga: só
          o imposto de caixa efetivo, e nada quando compensado ou dispensado.
        </div>
        <div className="flex flex-col gap-1 text-[12px]">
          {(dados?.perfis_tributarios ?? []).map((p) => (
            <div
              key={p.id}
              className="flex flex-col gap-1 rounded-md border border-border p-2"
              data-testid="perfil-tributario"
            >
              <div className="flex flex-wrap justify-between gap-2">
                <span>
                  <span className="font-semibold">{p.tipo_receita}</span> ·{" "}
                  {p.regime}
                  {p.municipio ? ` · ${p.municipio}` : ""}
                  {p.item_lista_servico
                    ? ` · item ${p.item_lista_servico}`
                    : ""}
                  {p.codigo_servico ? ` · código ${p.codigo_servico}` : ""}
                  {p.versao_legal ? ` · ${p.versao_legal}` : ""}
                </span>
                <span className="flex items-center gap-2">
                  de {p.vigente_de}{" "}
                  {p.vigente_ate ? `até ${p.vigente_ate}` : "(vigente)"}
                  <Button
                    type="button"
                    size="sm"
                    variant="ghost"
                    onClick={() =>
                      setTributosJson(JSON.stringify(p.componentes, null, 1))
                    }
                  >
                    Copiar
                  </Button>
                </span>
              </div>
              <div className="text-muted">
                {p.componentes.map(descreverTributo).join(" · ")}
              </div>
              {p.pendencias.length > 0 && (
                <Badge tone="amber">
                  A informar: {p.pendencias.join(", ")}
                </Badge>
              )}
            </div>
          ))}
          {dados?.perfis_tributarios.length === 0 && (
            <Badge tone="amber">
              Nenhum Tax Profile — comissões aguardando
            </Badge>
          )}
        </div>
        <form
          className="mt-2.5 grid grid-cols-1 gap-2 sm:grid-cols-4"
          onSubmit={(e) =>
            enviar(e, "/comissoes/perfis-tributarios", (f) => ({
              regime: String(f.get("regime")),
              vigente_de: String(f.get("vigente_de")),
              vigente_ate: String(f.get("vigente_ate") ?? "") || null,
              tipo_receita: String(f.get("tipo_receita")),
              municipio: String(f.get("municipio") ?? "") || null,
              codigo_servico: String(f.get("codigo_servico") ?? "") || null,
              item_lista_servico:
                String(f.get("item_lista_servico") ?? "") || null,
              versao_legal: String(f.get("versao_legal") ?? "") || null,
              componentes: lerJson(tributosJson),
              fonte: String(f.get("fonte") ?? "") || null,
            }))
          }
        >
          <Input name="regime" required defaultValue="LUCRO_PRESUMIDO" />
          <Input name="vigente_de" type="date" required />
          <Input name="vigente_ate" type="date" title="Fim (opcional)" />
          <Select name="tipo_receita">
            {(dados?.tipos_receita ?? ["*"]).map((t) => (
              <option key={t} value={t}>
                {t === "*" ? "Qualquer receita" : t}
              </option>
            ))}
          </Select>
          <Input name="municipio" placeholder="Município (ex.: São Paulo/SP)" />
          <Input
            name="item_lista_servico"
            placeholder="Item LC 116 (ex.: 1.05)"
          />
          <Input
            name="codigo_servico"
            placeholder="Código municipal (ex.: 2800)"
          />
          <Input
            name="versao_legal"
            placeholder="Versão legal (ex.: 2026-v1)"
          />
          <Input
            name="fonte"
            placeholder="Fonte (contador, parecer...)"
            className="sm:col-span-2"
          />
          <textarea
            required
            value={tributosJson}
            onChange={(e) => setTributosJson(e.target.value)}
            rows={4}
            placeholder={`Tributos (JSON; frações): [{"tributo":"IRPJ","base":"PRESUNCAO","aliquota":0.15,"presuncao":0.32}, ...] — tributos: ${(dados?.tributos ?? []).join(", ")}`}
            className="rounded-lg border border-border bg-surf px-2.5 py-2 font-mono text-[11px] text-text sm:col-span-4"
          />
          <Button type="submit" size="sm" className="sm:col-span-4">
            Salvar Tax Profile (nova versão)
          </Button>
        </form>
      </Card>

      <PainelInfraestrutura onAlterado={setMensagem} />

      <Card>
        <SectionLabel>Commission Policy</SectionLabel>
        <div className="flex flex-col gap-1 text-[12px] text-muted">
          <div data-testid="politica-margem">
            Margem (versão {dados?.politica_margem.versao}): impostos e
            infraestrutura sempre deduzidos; custo de IA{" "}
            <span className="font-semibold text-text">
              {dados?.politica_margem.regras.deduzir_custo_ia
                ? "deduzido"
                : "não deduzido"}
            </span>
            .
          </div>
          <div>Privado: {dados?.politica_privada}</div>
          <div>
            Government (versão {dados?.politica_governo.versao}, gatilho{" "}
            {dados?.politica_governo.regras.gatilho}):{" "}
            {Object.entries(dados?.politica_governo.regras.componentes ?? {})
              .map(
                ([tipo, regra]) =>
                  `${tipo} ${regra.comissionavel ? pct((regra.taxa ?? 0) * 100) : "não comissionável"}`,
              )
              .join(" · ")}
          </div>
        </div>
        <form
          className="mt-2.5 grid grid-cols-1 gap-2 sm:grid-cols-4"
          onSubmit={(e) =>
            enviar(e, "/comissoes/recalculo", (f) => ({
              motivo: String(f.get("motivo")),
            }))
          }
        >
          <Input
            name="motivo"
            required
            placeholder="Motivo do recálculo (auditoria)"
            className="sm:col-span-3"
          />
          <Button type="submit" size="sm" variant="ghost">
            Recalcular comissões não pagas
          </Button>
        </form>
        <form
          className="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-4"
          onSubmit={(e) =>
            enviar(e, "/comissoes/politica-margem", (f) => ({
              deduzir_custo_ia: f.get("deduzir_custo_ia") === "on",
              motivo: String(f.get("motivo")),
            }))
          }
        >
          <label className="flex items-center gap-1.5 text-[12px] text-muted">
            <input type="checkbox" name="deduzir_custo_ia" /> Deduzir custo de
            IA da margem
          </label>
          <Input
            name="motivo"
            required
            placeholder="Motivo da nova política (auditoria)"
            className="sm:col-span-2"
          />
          <Button type="submit" size="sm" variant="ghost">
            Nova versão da política
          </Button>
        </form>
      </Card>

      <Card data-testid="cambio">
        <SectionLabel>Câmbio (custos de IA em USD)</SectionLabel>
        <div className="flex flex-col gap-1 text-[12px]">
          {dados?.cotacao_vigente ? (
            <div>
              Vigente: {dados.cotacao_vigente.moeda_base}/
              {dados.cotacao_vigente.moeda_cotacao}{" "}
              {dados.cotacao_vigente.taxa.toLocaleString("pt-BR")} ·{" "}
              {dados.cotacao_vigente.fonte} · desde{" "}
              {dados.cotacao_vigente.vigente_em}
            </div>
          ) : (
            <Badge tone="amber">
              Sem cotação — custo de IA em reais: AWAITING_FX_RATE
            </Badge>
          )}
        </div>
        <form
          className="mt-2.5 grid grid-cols-1 gap-2 sm:grid-cols-4"
          onSubmit={(e) =>
            enviar(e, "/comissoes/cotacoes-cambio", (f) => ({
              moeda_base: "USD",
              moeda_cotacao: "BRL",
              taxa: Number(String(f.get("taxa")).replace(",", ".")),
              fonte: String(f.get("fonte")),
              vigente_em: String(f.get("vigente_em") ?? "") || null,
            }))
          }
        >
          <Input
            name="taxa"
            required
            placeholder="USD/BRL (ex.: cotação PTAX)"
          />
          <Input
            name="fonte"
            required
            placeholder="Fonte (ex.: PTAX venda BCB)"
          />
          <Input name="vigente_em" type="datetime-local" />
          <Button type="submit" size="sm">
            Registrar cotação
          </Button>
        </form>
      </Card>

      <Card data-testid="waterfall-comissoes">
        <div className="flex items-center justify-between gap-2">
          <SectionLabel>Waterfall financeira</SectionLabel>
          <Select
            value={agrupar}
            onChange={(e) => setAgrupar(e.target.value)}
            className="w-44"
          >
            {AGRUPAR.map(([valor, rotulo]) => (
              <option key={valor} value={valor}>
                Por {rotulo.toLowerCase()}
              </option>
            ))}
          </Select>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-[12px]">
            <thead>
              <tr className="border-b border-border text-[9.5px] tracking-wide text-muted uppercase">
                {[
                  "",
                  "Receita bruta",
                  "Impostos",
                  "Infra provisionada",
                  "Infra real",
                  "Custo de IA",
                  "Margem comissionável",
                  "Comissão",
                  "Margem CyberFort",
                  "Contribuição real",
                  "Contribuição conservadora",
                  "Reserva de infra",
                  "Aguardando",
                ].map((t) => (
                  <th key={t} className="p-2 text-left">
                    {t}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {[
                ...(waterfall?.linhas ?? []),
                ...(waterfall ? [waterfall.total] : []),
              ].map((l) => (
                <tr key={String(l.chave)} className="border-b border-border">
                  <td className="p-2 font-semibold">
                    {l.chave ?? "sem representante"}
                  </td>
                  <td className="p-2">{brl(l.receita_bruta)}</td>
                  <td className="p-2">
                    {brl(l.impostos)}{" "}
                    <span className="text-muted">
                      {pct(l.percentuais.impostos)}
                    </span>
                  </td>
                  <td className="p-2">
                    {brl(l.infraestrutura)}{" "}
                    <span className="text-muted">
                      {pct(l.percentuais.infraestrutura)}
                    </span>
                  </td>
                  <td className="p-2" data-testid="infra-real">
                    {l.infraestrutura_real_incompleta
                      ? "—"
                      : brl(l.infraestrutura_real)}
                  </td>
                  <td className="p-2">{brl(l.custo_ia)}</td>
                  <td className="p-2">
                    {brl(l.margem_comissionavel_liquida)}{" "}
                    <span className="text-muted">
                      {pct(l.percentuais.margem_comissionavel_liquida)}
                    </span>
                  </td>
                  <td className="p-2">
                    {brl(l.comissao)}{" "}
                    <span className="text-muted">
                      {pct(l.percentuais.comissao)}
                    </span>
                  </td>
                  <td className="p-2">
                    {brl(l.margem_cyberfort_apos_comissao)}{" "}
                    <span className="text-muted">
                      {pct(l.percentuais.margem_cyberfort_apos_comissao)}
                    </span>
                  </td>
                  <td className="p-2">
                    {l.margem_contribuicao_real === null
                      ? "—"
                      : brl(l.margem_contribuicao_real)}
                  </td>
                  <td className="p-2">
                    {brl(l.margem_contribuicao_conservadora)}
                  </td>
                  <td className="p-2">
                    {l.reserva_infraestrutura === null
                      ? "—"
                      : brl(l.reserva_infraestrutura)}
                  </td>
                  <td className="p-2 text-muted">
                    {l.aguardando_parametros
                      ? brl(l.aguardando_parametros)
                      : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {waterfall && (
          <div className="mt-2 flex flex-col gap-1 text-[11px] text-muted">
            <div data-testid="impostos-por-tributo">
              Impostos por tributo:{" "}
              {Object.entries(waterfall.total.impostos_por_tributo)
                .map(([t, v]) => `${t} ${brl(v)}`)
                .join(" · ") || "—"}
            </div>
            <div>
              Aguardando por parâmetro:{" "}
              {Object.entries(waterfall.total.aguardando_por_parametro)
                .map(([status, n]) => `${status}: ${n}`)
                .join(" · ") || "nenhum"}
            </div>
          </div>
        )}
      </Card>
    </div>
  );
}
