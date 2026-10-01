import { useCallback, useEffect, useState, type FormEvent } from "react";

import { ResumoParametrosComissao } from "@/components/ResumoParametrosComissao";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, SectionLabel } from "@/components/ui/Card";
import { Input, Select } from "@/components/ui/Input";
import { AcessoRestrito } from "@/pages/admin/AcessoRestrito";
import { brl } from "@/lib/aiCredits";
import { api, mensagemErro } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { OfertaGoverno } from "@/lib/catalogo";
import {
  data,
  ROTULO_COMPONENTE,
  ROTULO_MODELO,
  type ContratoGoverno,
} from "@/lib/governo";

interface Metricas {
  bookings: Record<
    "licenca" | "servicos" | "assinatura" | "creditos" | "total",
    number
  >;
  new_arr: number;
  renewal_arr: number;
  arr_governo: number;
  tcv_inicial: number;
  cash_in: number;
  receita_comissionavel: number;
  receita_nao_comissionavel: number;
  comissoes: {
    inicial: number;
    renovacao: number;
    reconhecida: number;
    paga: number;
    pendente: number;
    a_compensar: number;
  };
  pipeline: {
    oportunidades_abertas: number;
    tcv_estimado: number;
    pipeline_ponderado: number;
  } | null;
}

interface Oportunidade {
  id: number;
  titulo: string;
  entidade_governamental: string;
  estagio: string;
  data_prevista_fechamento: string | null;
  tcv_estimado: number;
  probabilidade: number;
  pipeline_ponderado: number;
}

interface Comissao {
  id: number;
  representante_id: number;
  componente_tipo: string;
  numero_renovacao: number | null;
  apuracao_id: number | null;
  base_calculo: number | null;
  taxa: number;
  evento: string;
  valor: number;
  status: string;
}

interface Representante {
  id: number;
  nome: string;
}

const num = (form: FormData, campo: string) => {
  const texto = String(form.get(campo) ?? "").trim();
  return texto ? Number(texto) : null;
};

function Indicador({ rotulo, valor }: { rotulo: string; valor: string }) {
  return (
    <Card>
      <SectionLabel>{rotulo}</SectionLabel>
      <div className="font-head text-lg font-bold text-text">{valor}</div>
    </Card>
  );
}

function DetalheContrato({
  contrato,
  onMudou,
}: {
  contrato: ContratoGoverno;
  onMudou: () => void;
}) {
  const [comissoes, setComissoes] = useState<Comissao[]>([]);
  const [erro, setErro] = useState<string | null>(null);

  const carregar = useCallback(() => {
    api
      .get<Comissao[]>(`/governo/comissoes?contrato_id=${contrato.id}`)
      .then(setComissoes)
      .catch(() => setComissoes([]));
  }, [contrato.id]);

  useEffect(carregar, [carregar]);

  async function enviar(
    evento: FormEvent<HTMLFormElement>,
    rota: string,
    corpo: (form: FormData) => object,
  ) {
    evento.preventDefault();
    const formulario = evento.currentTarget;
    try {
      await api.post(rota, corpo(new FormData(formulario)));
      formulario.reset();
      setErro(null);
      onMudou();
      carregar();
    } catch (error) {
      setErro(mensagemErro(error, "Não foi possível salvar."));
    }
  }

  return (
    <div className="flex flex-col gap-3 border-t border-border pt-3 text-[12px]">
      {erro && <div className="text-red">{erro}</div>}
      <div className="grid grid-cols-1 gap-1 sm:grid-cols-2">
        {contrato.componentes.map((c) => (
          <div
            key={c.id}
            className="flex justify-between gap-2 rounded-md border border-border p-2"
          >
            <span>
              {ROTULO_COMPONENTE[c.tipo] ?? c.tipo}
              {c.comissionavel && (
                <span className="text-muted">
                  {" "}
                  · comissão {Math.round((c.taxa_comissao ?? 0) * 100)}%
                </span>
              )}
              {c.cancelado && <Badge tone="red">cancelado</Badge>}
            </span>
            <span>
              {brl(c.valor)}{" "}
              <span className="text-muted">/ recebido {brl(c.recebido)}</span>
            </span>
          </div>
        ))}
      </div>
      <div className="text-muted">
        {contrato.periodos.map((p) => (
          <div key={p.id}>
            Período {p.numero}: {data(p.inicio)} a {data(p.fim)} ·{" "}
            {brl(p.valor_assinatura)}/ano · {p.status} · renovação{" "}
            {p.status_renovacao}
            {p.creditos &&
              ` · AI Credits ${p.creditos.credits_remaining.toLocaleString("pt-BR")}/${p.creditos.annual_credit_pool.toLocaleString("pt-BR")}`}
          </div>
        ))}
      </div>
      <form
        className="grid grid-cols-1 gap-2 sm:grid-cols-5"
        onSubmit={(e) =>
          enviar(e, `/governo/contratos/${contrato.id}/recebimentos`, (f) => ({
            componente_id: Number(f.get("componente_id")),
            valor: num(f, "valor"),
            recebido_em: String(f.get("recebido_em")),
            referencia: String(f.get("referencia") ?? "") || null,
          }))
        }
      >
        <Select name="componente_id" className="sm:col-span-2">
          {contrato.componentes
            .filter((c) => !c.cancelado)
            .map((c) => (
              <option key={c.id} value={c.id}>
                {ROTULO_COMPONENTE[c.tipo] ?? c.tipo} ({brl(c.valor)})
              </option>
            ))}
        </Select>
        <Input
          name="valor"
          type="number"
          min={0}
          step="0.01"
          required
          placeholder="Valor recebido"
        />
        <Input name="recebido_em" type="date" required />
        <Button type="submit" size="sm">
          Registrar recebimento
        </Button>
        <Input
          name="referencia"
          placeholder="NF / ordem bancária (opcional)"
          className="sm:col-span-5"
        />
      </form>
      <form
        className="grid grid-cols-1 gap-2 sm:grid-cols-4"
        onSubmit={(e) =>
          enviar(e, `/governo/contratos/${contrato.id}/renovacoes`, (f) => ({
            valor_assinatura: num(f, "valor_assinatura"),
            motivo_reajuste: String(f.get("motivo_reajuste") ?? "") || null,
          }))
        }
      >
        <Input
          name="valor_assinatura"
          type="number"
          min={0}
          step="0.01"
          placeholder="Valor da renovação (vazio = mesmo)"
        />
        <Input
          name="motivo_reajuste"
          placeholder="Regra contratual do reajuste"
          className="sm:col-span-2"
        />
        <Button type="submit" size="sm" variant="ghost">
          Renovar subscrição
        </Button>
      </form>
      <div>
        <SectionLabel>Comissões</SectionLabel>
        {comissoes.length === 0 ? (
          <div className="text-muted">
            Nenhuma comissão (com o gatilho atual, só nasce com recebimento).
          </div>
        ) : (
          comissoes.map((c) => (
            <div key={c.id} className="flex justify-between gap-2">
              <span>
                Rep. {c.representante_id} ·{" "}
                {ROTULO_COMPONENTE[c.componente_tipo] ?? c.componente_tipo}
                {c.numero_renovacao ? ` #${c.numero_renovacao}` : ""} ·{" "}
                {c.status === "AWAITING_COST_PARAMETERS"
                  ? "margem aguardando parâmetros de custo"
                  : `margem ${brl(c.base_calculo ?? 0)}`}{" "}
                × {Math.round(c.taxa * 100)}%
              </span>
              <span>
                {brl(c.valor)}{" "}
                <Badge tone={c.status === "PAID" ? "green" : c.status === "AWAITING_COST_PARAMETERS" ? "amber" : "muted"}>
                  {c.status}
                </Badge>
              </span>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

/** Operação B2B ON Government (D-072, super_admin): pipeline, contratos, recebimentos, renovação, comissões e
 * métricas (Bookings, ARR, TCV e Cash-In separados). */
export function AdminGoverno() {
  const { usuario } = useAuth();
  const [metricas, setMetricas] = useState<Metricas | null>(null);
  const [ofertas, setOfertas] = useState<OfertaGoverno[]>([]);
  const [contratos, setContratos] = useState<ContratoGoverno[]>([]);
  const [oportunidades, setOportunidades] = useState<{
    estagios: string[];
    itens: Oportunidade[];
  } | null>(null);
  const [representantes, setRepresentantes] = useState<Representante[]>([]);
  const [aberto, setAberto] = useState<number | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const isSuperAdmin = usuario?.papel === "super_admin";

  const carregar = useCallback(async () => {
    try {
      const [m, o, c, p, r] = await Promise.all([
        api.get<Metricas>("/governo/metricas"),
        api.get<OfertaGoverno[]>("/governo/planos"),
        api.get<ContratoGoverno[]>("/governo/contratos"),
        api.get<{ estagios: string[]; itens: Oportunidade[] }>(
          "/governo/oportunidades",
        ),
        api.get<Representante[]>("/representantes"),
      ]);
      setMetricas(m);
      setOfertas(o);
      setContratos(c);
      setOportunidades(p);
      setRepresentantes(r);
    } catch (error) {
      setErro(mensagemErro(error, "Não foi possível carregar o Government."));
    }
  }, []);

  useEffect(() => {
    if (isSuperAdmin) carregar();
  }, [isSuperAdmin, carregar]);

  async function criarContrato(evento: FormEvent<HTMLFormElement>) {
    evento.preventDefault();
    const f = new FormData(evento.currentTarget);
    const soAssinatura =
      f.get("modelo_cobranca") === "GOVERNMENT_ANNUAL_SUBSCRIPTION_ONLY";
    try {
      await api.post("/governo/contratos", {
        tenant_id: String(f.get("tenant_id")),
        plano_id: Number(f.get("plano_id")),
        modelo_cobranca: String(f.get("modelo_cobranca")),
        referencia_contrato: String(f.get("referencia_contrato")),
        entidade_governamental: String(f.get("entidade_governamental")),
        assinado_em: String(f.get("assinado_em")),
        representante_id: num(f, "representante_id"),
        valores: soAssinatura
          ? {
              implantacao: num(f, "implantacao"),
              assinatura_anual: num(f, "assinatura_anual"),
              creditos_ia_anuais: num(f, "creditos"),
            }
          : null,
      });
      setErro(null);
      carregar();
    } catch (error) {
      setErro(mensagemErro(error, "Não foi possível criar o contrato."));
    }
  }

  async function criarOportunidade(evento: FormEvent<HTMLFormElement>) {
    evento.preventDefault();
    const formulario = evento.currentTarget;
    const f = new FormData(formulario);
    try {
      await api.post("/governo/oportunidades", {
        titulo: String(f.get("titulo")),
        entidade_governamental: String(f.get("entidade_governamental")),
        estagio: String(f.get("estagio")),
        data_prevista_fechamento:
          String(f.get("data_prevista_fechamento") ?? "") || null,
        valor_estimado_licenca: num(f, "valor_estimado_licenca") ?? 0,
        valor_estimado_assinatura: num(f, "valor_estimado_assinatura") ?? 0,
        valor_estimado_servicos: num(f, "valor_estimado_servicos") ?? 0,
        probabilidade: (num(f, "probabilidade") ?? 0) / 100,
      });
      formulario.reset();
      carregar();
    } catch (error) {
      setErro(mensagemErro(error, "Não foi possível criar a oportunidade."));
    }
  }

  if (!isSuperAdmin) return <AcessoRestrito />;

  return (
    <div className="flex flex-col gap-4 p-5.5" data-testid="admin-governo">
      <div>
        <div className="font-head text-xl font-bold">
          Admin — B2B ON Government
        </div>
        <div className="mt-0.5 text-[11px] text-muted">
          Licença, implantação e subscrição anual separadas. ARR é só
          subscrição; Cash-In é só o que foi recebido.
        </div>
      </div>
      {erro && <div className="text-[12px] text-red">{erro}</div>}
      <ResumoParametrosComissao />

      {metricas && (
        <div
          className="grid grid-cols-2 gap-3 lg:grid-cols-4"
          data-testid="metricas-governo"
        >
          <Indicador
            rotulo="ARR Government"
            valor={brl(metricas.arr_governo)}
          />
          <Indicador rotulo="New ARR" valor={brl(metricas.new_arr)} />
          <Indicador rotulo="Renewal ARR" valor={brl(metricas.renewal_arr)} />
          <Indicador rotulo="TCV inicial" valor={brl(metricas.tcv_inicial)} />
          <Indicador
            rotulo="Bookings de licença"
            valor={brl(metricas.bookings.licenca)}
          />
          <Indicador
            rotulo="Bookings de serviços"
            valor={brl(metricas.bookings.servicos)}
          />
          <Indicador
            rotulo="Bookings de subscrição"
            valor={brl(metricas.bookings.assinatura)}
          />
          <Indicador rotulo="Cash-In" valor={brl(metricas.cash_in)} />
          <Indicador
            rotulo="Comissão inicial"
            valor={brl(metricas.comissoes.inicial)}
          />
          <Indicador
            rotulo="Comissão de renovação"
            valor={brl(metricas.comissoes.renovacao)}
          />
          <Indicador
            rotulo="Comissão paga / pendente"
            valor={`${brl(metricas.comissoes.paga)} / ${brl(metricas.comissoes.pendente)}`}
          />
          <Indicador
            rotulo="Pipeline ponderado"
            valor={
              metricas.pipeline
                ? brl(metricas.pipeline.pipeline_ponderado)
                : "—"
            }
          />
        </div>
      )}

      <Card>
        <SectionLabel>
          Pipeline Government (separado da quota de New MRR)
        </SectionLabel>
        <div className="flex flex-col gap-1 text-[12px]">
          {(oportunidades?.itens ?? []).map((o) => (
            <div
              key={o.id}
              className="flex flex-wrap justify-between gap-2 rounded-md border border-border p-2"
            >
              <span>
                <span className="font-semibold">{o.titulo}</span>
                <span className="text-muted">
                  {" "}
                  · {o.entidade_governamental} · fechamento{" "}
                  {data(o.data_prevista_fechamento)}
                </span>
              </span>
              <span>
                <Badge>{o.estagio}</Badge> TCV {brl(o.tcv_estimado)} ·{" "}
                {Math.round(o.probabilidade * 100)}% · ponderado{" "}
                {brl(o.pipeline_ponderado)}
              </span>
            </div>
          ))}
        </div>
        <form
          onSubmit={criarOportunidade}
          className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-4"
        >
          <Input name="titulo" required placeholder="Oportunidade" />
          <Input
            name="entidade_governamental"
            required
            placeholder="Órgão / entidade"
          />
          <Select name="estagio">
            {(oportunidades?.estagios ?? []).map((e) => (
              <option key={e} value={e}>
                {e}
              </option>
            ))}
          </Select>
          <Input name="data_prevista_fechamento" type="date" />
          <Input
            name="valor_estimado_licenca"
            type="number"
            min={0}
            placeholder="Licença estimada"
          />
          <Input
            name="valor_estimado_assinatura"
            type="number"
            min={0}
            placeholder="Subscrição estimada"
          />
          <Input
            name="valor_estimado_servicos"
            type="number"
            min={0}
            placeholder="Serviços estimados"
          />
          <Input
            name="probabilidade"
            type="number"
            min={0}
            max={100}
            placeholder="Probabilidade (%)"
          />
          <Button type="submit" size="sm" className="sm:col-span-4">
            Adicionar oportunidade
          </Button>
        </form>
      </Card>

      <Card>
        <SectionLabel>Contratos</SectionLabel>
        <div className="flex flex-col gap-2">
          {contratos.map((c) => (
            <div
              key={c.id}
              className="rounded-md border border-border p-2.5 text-[12px]"
              data-testid="contrato-governo-admin"
            >
              <button
                type="button"
                className="flex w-full flex-wrap justify-between gap-2 text-left"
                onClick={() => setAberto(aberto === c.id ? null : c.id)}
              >
                <span>
                  <span className="font-semibold">{c.referencia_contrato}</span>
                  <span className="text-muted">
                    {" "}
                    · {c.entidade_governamental} · {c.tenant_id} ·{" "}
                    {ROTULO_MODELO[c.modelo_cobranca] ?? c.modelo_cobranca}
                  </span>
                </span>
                <span>
                  Contratação inicial {brl(c.valores.contratacao_inicial)}{" "}
                  <Badge>{c.status}</Badge>
                </span>
              </button>
              {aberto === c.id && (
                <DetalheContrato contrato={c} onMudou={carregar} />
              )}
            </div>
          ))}
          {contratos.length === 0 && (
            <div className="text-[12px] text-muted">Nenhum contrato.</div>
          )}
        </div>
        <form
          onSubmit={criarContrato}
          className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-4"
        >
          <Input name="tenant_id" required placeholder="Tenant do órgão" />
          <Select name="plano_id">
            {ofertas.map((o) => (
              <option key={o.id} value={o.id}>
                {o.nome}
              </option>
            ))}
          </Select>
          <Select name="modelo_cobranca">
            {Object.entries(ROTULO_MODELO).map(([valor, rotulo]) => (
              <option key={valor} value={valor}>
                {rotulo}
              </option>
            ))}
          </Select>
          <Select name="representante_id">
            <option value="">Sem representante (venda direta)</option>
            {representantes.map((r) => (
              <option key={r.id} value={r.id}>
                {r.nome}
              </option>
            ))}
          </Select>
          <Input
            name="referencia_contrato"
            required
            placeholder="Nº do contrato / processo"
          />
          <Input
            name="entidade_governamental"
            required
            placeholder="Órgão contratante"
          />
          <Input name="assinado_em" type="date" required />
          <div />
          <Input
            name="implantacao"
            type="number"
            min={0}
            placeholder="Implantação (só subscrição)"
          />
          <Input
            name="assinatura_anual"
            type="number"
            min={0}
            placeholder="Subscrição anual (só subscrição)"
          />
          <Input
            name="creditos"
            type="number"
            min={0}
            placeholder="AI Credits/ano (só subscrição)"
          />
          <Button type="submit" size="sm">
            Criar contrato
          </Button>
        </form>
      </Card>
    </div>
  );
}
