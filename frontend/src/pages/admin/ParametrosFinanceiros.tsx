import { useCallback, useEffect, useState, type FormEvent } from "react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, SectionLabel } from "@/components/ui/Card";
import { Input, Select } from "@/components/ui/Input";
import { AcessoRestrito } from "@/pages/admin/AcessoRestrito";
import { brl } from "@/lib/aiCredits";
import { api, mensagemErro } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { pct, type Parametros, type Waterfall } from "@/lib/comissoes";

const AGRUPAR = [
  ["tenant", "Tenant"],
  ["representante", "Representante"],
  ["produto", "Produto"],
  ["venda", "Venda"],
  ["periodo", "Período"],
] as const;

const fracao = (form: FormData, campo: string) => {
  const texto = String(form.get(campo) ?? "").trim();
  return texto ? Number(texto) / 100 : null;
};

/** "IRPJ=4,8; CSLL=2,88" → componentes com alíquota em fração. */
function lerComponentes(texto: string) {
  return texto
    .split(/[;\n]/)
    .map((parte) => parte.trim())
    .filter(Boolean)
    .map((parte) => {
      const [nome, valor] = parte.split("=");
      return {
        nome: nome.trim(),
        aliquota: Number(String(valor ?? "").replace(",", ".")) / 100,
      };
    });
}

/** Parâmetros financeiros do Commission Engine (D-074): Tax Profile, Infrastructure Cost Model, política e waterfall.
 * Nenhum valor vem pronto: o PO informa, com vigência; o histórico só muda por recálculo explícito. */
export function ParametrosFinanceiros() {
  const { usuario } = useAuth();
  const [dados, setDados] = useState<Parametros | null>(null);
  const [waterfall, setWaterfall] = useState<Waterfall | null>(null);
  const [agrupar, setAgrupar] = useState("tenant");
  const [mensagem, setMensagem] = useState<string | null>(null);
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
      const resposta = await api.post<{
        aguardando_calculadas?: number;
        alteradas?: number;
      }>(rota, corpo(new FormData(formulario)));
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
          atribuíveis − infraestrutura atribuível) × taxa. Sem Tax Profile ou
          modelo de infraestrutura vigente, a comissão fica aguardando e não é
          paga.
        </div>
      </div>
      {mensagem && <div className="text-[12px] text-muted">{mensagem}</div>}

      <Card>
        <SectionLabel>Tax Profile (carga tributária atribuível)</SectionLabel>
        <div className="flex flex-col gap-1 text-[12px]">
          {(dados?.perfis_tributarios ?? []).map((p) => (
            <div
              key={p.id}
              className="flex flex-wrap justify-between gap-2 rounded-md border border-border p-2"
            >
              <span>
                <span className="font-semibold">{p.regime}</span> ·{" "}
                {p.tipo_receita} ·{" "}
                {p.componentes
                  .map((c) => `${c.nome} ${pct(c.aliquota * 100)}`)
                  .join(", ")}
              </span>
              <span>
                efetiva {pct(Math.round(p.aliquota_efetiva * 10000) / 100)} · de{" "}
                {p.vigente_de}{" "}
                {p.vigente_ate ? `até ${p.vigente_ate}` : "(vigente)"}
              </span>
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
              tipo_receita: String(f.get("tipo_receita")),
              municipio: String(f.get("municipio") ?? "") || null,
              componentes: lerComponentes(String(f.get("componentes"))),
              fonte: String(f.get("fonte") ?? "") || null,
            }))
          }
        >
          <Input name="regime" required defaultValue="LUCRO_PRESUMIDO" />
          <Input name="vigente_de" type="date" required />
          <Select name="tipo_receita">
            {(dados?.tipos_receita ?? ["*"]).map((t) => (
              <option key={t} value={t}>
                {t === "*" ? "Qualquer receita" : t}
              </option>
            ))}
          </Select>
          <Input name="municipio" placeholder="Município (opcional)" />
          <Input
            name="componentes"
            required
            placeholder="Componentes em %: IRPJ=…; CSLL=…; PIS=…; COFINS=…; ISS=…"
            className="sm:col-span-3"
          />
          <Input name="fonte" placeholder="Fonte (contador, parecer...)" />
          <Button type="submit" size="sm" className="sm:col-span-4">
            Salvar Tax Profile
          </Button>
        </form>
      </Card>

      <Card>
        <SectionLabel>
          Infrastructure Cost Model (custo atribuível à receita)
        </SectionLabel>
        <div className="flex flex-col gap-1 text-[12px]">
          {(dados?.modelos_custo_infra ?? []).map((m) => (
            <div
              key={m.id}
              className="flex flex-wrap justify-between gap-2 rounded-md border border-border p-2"
            >
              <span>
                <span className="font-semibold">{m.nome}</span> · {m.metodo} ·{" "}
                {JSON.stringify(m.componentes)}
              </span>
              <span>
                de {m.vigente_de}{" "}
                {m.vigente_ate ? `até ${m.vigente_ate}` : "(vigente)"}
              </span>
            </div>
          ))}
          {dados?.modelos_custo_infra.length === 0 && (
            <Badge tone="amber">Nenhum modelo — comissões aguardando</Badge>
          )}
        </div>
        <form
          className="mt-2.5 grid grid-cols-1 gap-2 sm:grid-cols-4"
          onSubmit={(e) =>
            enviar(e, "/comissoes/modelos-custo-infra", (f) => {
              const componentes: Record<string, unknown>[] = [];
              const percentual = fracao(f, "percentual");
              if (percentual !== null)
                componentes.push({ tipo: "PERCENTUAL", percentual });
              const fixo = String(f.get("fixo") ?? "").trim();
              if (fixo)
                componentes.push({
                  tipo: "FIXO_POR_RECEBIMENTO",
                  valor: Number(fixo),
                });
              if (f.get("uso_ia") === "on")
                componentes.push({
                  tipo: "USO_IA",
                  janela_dias: Number(f.get("janela_dias") || 30),
                });
              const extra = String(f.get("extra") ?? "").trim();
              if (extra)
                componentes.push(
                  ...(JSON.parse(extra) as Record<string, unknown>[]),
                );
              return {
                nome: String(f.get("nome")),
                vigente_de: String(f.get("vigente_de")),
                componentes,
                fonte: String(f.get("fonte") ?? "") || null,
              };
            })
          }
        >
          <Input name="nome" required placeholder="Nome do modelo" />
          <Input name="vigente_de" type="date" required />
          <Input
            name="percentual"
            type="number"
            min={0}
            max={99}
            step="0.01"
            placeholder="% da receita"
          />
          <Input
            name="fixo"
            type="number"
            min={0}
            step="0.01"
            placeholder="R$ fixo por recebimento"
          />
          <label className="flex items-center gap-1.5 text-[12px] text-muted">
            <input type="checkbox" name="uso_ia" /> Custo real de IA do tenant
            (não use se o % já inclui IA)
          </label>
          <Input
            name="janela_dias"
            type="number"
            min={1}
            placeholder="Janela IA (dias)"
          />
          <Input
            name="extra"
            placeholder='Opcional: [{"tipo":"POR_PRODUTO","percentuais":{"GOVERNMENT":0.04}}]'
            className="sm:col-span-2"
          />
          <Input
            name="fonte"
            placeholder="Fonte (cloud, banco...)"
            className="sm:col-span-2"
          />
          <Button type="submit" size="sm" className="sm:col-span-2">
            Salvar modelo
          </Button>
        </form>
      </Card>

      <Card>
        <SectionLabel>Commission Policy</SectionLabel>
        <div className="flex flex-col gap-1 text-[12px] text-muted">
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
                  "Infraestrutura",
                  "Margem comissionável",
                  "Comissão",
                  "Margem CyberFort",
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
      </Card>
    </div>
  );
}
