import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, SectionLabel } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { KpiCard } from "@/components/ui/KpiCard";
import { api, ApiError } from "@/lib/api";
import { brl, creditos, type Pacote } from "@/lib/aiCredits";
import { useAuth } from "@/lib/auth";

/** B2B ON AI Credits — carteira do cliente (Fase 15).
 * Mostra créditos, nunca custo do provedor. Preço dos pacotes vem da API
 * (catálogo versionado); nada de preço fixo no código. */

interface Carteira {
  disponivel: number;
  reservado: number;
  incluido_no_plano: number;
  comprado: number;
  promocional: number;
  ajustes: number;
  a_vencer_30_dias: { tipo: string; quantidade: number; expira_em: string }[];
  franquia_mensal: number;
  franquia_detalhe: {
    produto: string;
    creditos: number | null;
    status: string;
  }[];
  uso_do_mes: {
    periodo: string;
    consumido: number;
    total_do_periodo: number;
    percentual: number | null;
    dias_restantes_estimados: number | null;
  };
  modo: string;
}

interface Agrupado {
  chave: string;
  execucoes: number;
  creditos: number;
}

interface Consumo {
  por_modulo: Agrupado[];
  por_workload: Agrupado[];
  por_agente: Agrupado[];
}

interface Compra {
  id: number;
  pacote: string;
  creditos: number;
  preco: number;
  status: string;
  origem: string;
  url_checkout: string | null;
  criado_em: string | null;
}

interface Recarga {
  ativa: boolean;
  limiar: number | null;
  pacote: string | null;
  consentido_em: string | null;
}

interface Orcamento {
  orcamento_mensal_creditos: number | null;
  limite_diario_creditos: number | null;
  limite_usuario_creditos: number | null;
  limite_api_creditos: number | null;
  limites_modulo_percentual: Record<string, number> | null;
  percentual_alerta: number;
  parada_rigida: boolean;
}

interface Alerta {
  periodo: string;
  nivel: number;
  percentual: number;
  tipo: string;
}

const ROTULO_TIPO: Record<string, string> = {
  SUBSCRIPTION: "Incluídos no plano",
  TOPUP: "Comprados",
  PROMOTIONAL: "Promocionais",
  ADJUSTMENT: "Ajustes",
};

const data = (iso: string | null) =>
  iso ? new Date(iso).toLocaleDateString("pt-BR") : "—";

function Tabela({ titulo, linhas }: { titulo: string; linhas: Agrupado[] }) {
  return (
    <Card>
      <SectionLabel>{titulo}</SectionLabel>
      {linhas.map((linha) => (
        <div
          key={linha.chave}
          className="flex justify-between border-b border-border py-1.5 text-[12px]"
        >
          <span>{linha.chave}</span>
          <span className="text-muted">
            {linha.execucoes} uso(s) ·{" "}
            <b className="text-text">{creditos(linha.creditos)}</b>
          </span>
        </div>
      ))}
      {linhas.length === 0 && (
        <div className="text-[12px] text-muted">
          Sem consumo nos últimos 30 dias.
        </div>
      )}
    </Card>
  );
}

function BarraUso({ uso }: { uso: Carteira["uso_do_mes"] }) {
  const percentual = uso.percentual ?? 0;
  const cor =
    percentual >= 95 ? "bg-red" : percentual >= 80 ? "bg-amber" : "bg-cyan";
  return (
    <Card className="mb-4">
      <SectionLabel>Uso do mês ({uso.periodo})</SectionLabel>
      <div className="mb-1.5 flex justify-between text-[12px]">
        <span className="text-muted">
          {creditos(uso.consumido)} de {creditos(uso.total_do_periodo)}
        </span>
        <b>
          {uso.percentual === null
            ? "—"
            : `${uso.percentual.toLocaleString("pt-BR")}%`}
        </b>
      </div>
      <div className="h-2 rounded-full bg-surf2">
        <div
          className={`h-2 rounded-full ${cor}`}
          style={{ width: `${Math.min(percentual, 100)}%` }}
        />
      </div>
      <div className="mt-1.5 text-[11px] text-muted">
        {uso.dias_restantes_estimados === null
          ? "Estimativa de dias restantes aparece após alguns dias de uso."
          : `No ritmo atual, os créditos disponíveis duram cerca de ${uso.dias_restantes_estimados} dia(s).`}{" "}
        Avisos em 80%, 95% e 100%.
      </div>
    </Card>
  );
}

function ComprarPacotes({
  aoComprar,
}: {
  aoComprar: (compra: Compra) => void;
}) {
  const [pacotes, setPacotes] = useState<Pacote[]>([]);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => {
    api
      .get<{ pacotes: Pacote[] }>("/ai-credits/pacotes")
      .then((r) => setPacotes(r.pacotes))
      .catch(() => setErro("Não foi possível carregar os pacotes."));
  }, []);

  async function comprar(codigo: string) {
    try {
      const compra = await api.post<Compra>("/ai-credits/compras", {
        pacote: codigo,
      });
      aoComprar(compra);
      if (compra.url_checkout) window.location.href = compra.url_checkout;
    } catch (error) {
      setErro(
        error instanceof ApiError
          ? error.message
          : "Não foi possível iniciar a compra.",
      );
    }
  }

  return (
    <Card className="mb-4">
      <SectionLabel>Comprar AI Credits</SectionLabel>
      <div className="mb-2 text-[11px] text-muted">
        Créditos comprados valem por 12 meses e entram na carteira da empresa
        assim que o pagamento é confirmado.
      </div>
      {erro && <div className="mb-2 text-[12px] text-red">{erro}</div>}
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        {pacotes.map((pacote) => (
          <div
            key={pacote.codigo}
            className="flex flex-col gap-1 rounded-lg border border-border p-3 text-[12px]"
          >
            <b>{pacote.nome}</b>
            {pacote.status === "CONTACT_SALES" ? (
              <>
                <span className="text-muted">Volume sob medida</span>
                <a
                  className="mt-auto font-semibold text-cyan hover:underline"
                  href="mailto:comercial@cyberfort.com.br?subject=AI%20Credits%20Enterprise"
                >
                  Falar com vendas
                </a>
              </>
            ) : (
              <>
                <span>{creditos(pacote.creditos ?? 0)}</span>
                <span className="font-head text-[18px] font-bold">
                  {brl(pacote.preco ?? 0)}
                </span>
                <span className="text-[10.5px] text-muted">
                  {pacote.preco_efetivo_por_1000 !== null
                    ? `${brl(pacote.preco_efetivo_por_1000)} por 1.000`
                    : ""}
                </span>
                <Button
                  size="sm"
                  className="mt-1"
                  onClick={() => comprar(pacote.codigo)}
                >
                  Comprar
                </Button>
              </>
            )}
          </div>
        ))}
      </div>
    </Card>
  );
}

function RecargaAutomatica({ pacotes }: { pacotes: Pacote[] }) {
  const [recarga, setRecarga] = useState<Recarga | null>(null);
  const [mensagem, setMensagem] = useState<string | null>(null);

  useEffect(() => {
    api
      .get<Recarga>("/ai-credits/recarga-automatica")
      .then(setRecarga)
      .catch(() => undefined);
  }, []);

  async function salvar(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const ativa = form.get("ativa") === "on";
    try {
      setRecarga(
        await api.put<Recarga>("/ai-credits/recarga-automatica", {
          ativa,
          limiar: ativa ? Number(form.get("limiar")) : null,
          pacote: ativa ? String(form.get("pacote")) : null,
          consentimento: form.get("consentimento") === "on",
        }),
      );
      setMensagem("Configuração salva.");
    } catch (error) {
      setMensagem(
        error instanceof ApiError ? error.message : "Não foi possível salvar.",
      );
    }
  }

  if (!recarga) return null;
  return (
    <Card>
      <SectionLabel>Recarga automática</SectionLabel>
      <div className="mb-2 text-[11px] text-muted">
        Quando o saldo ficar abaixo do limite, criamos o pedido do pacote
        escolhido e avisamos o administrador para concluir o pagamento. Nada é
        cobrado sem o seu consentimento.
      </div>
      <form onSubmit={salvar} className="flex flex-col gap-2 text-[12px]">
        <label className="flex items-center gap-1.5">
          <input type="checkbox" name="ativa" defaultChecked={recarga.ativa} />{" "}
          Ativar recarga automática
        </label>
        <div className="flex flex-wrap gap-2">
          <Input
            name="limiar"
            type="number"
            min="1"
            defaultValue={recarga.limiar ?? ""}
            placeholder="Recarregar abaixo de (créditos)"
          />
          <select
            name="pacote"
            defaultValue={recarga.pacote ?? ""}
            className="rounded-md border border-border bg-transparent px-2 py-1.5"
          >
            {pacotes
              .filter((p) => p.status === "ATIVO")
              .map((p) => (
                <option key={p.codigo} value={p.codigo}>
                  {p.nome} — {creditos(p.creditos ?? 0)} por {brl(p.preco ?? 0)}
                </option>
              ))}
          </select>
        </div>
        <label className="flex items-start gap-1.5">
          <input type="checkbox" name="consentimento" className="mt-0.5" />
          <span>
            Autorizo a criação automática de pedidos de AI Credits no valor do
            pacote escolhido.
          </span>
        </label>
        <div className="flex items-center gap-2">
          <Button size="sm" type="submit">
            Salvar
          </Button>
          {recarga.consentido_em && (
            <span className="text-[11px] text-muted">
              Consentimento registrado em {data(recarga.consentido_em)}
            </span>
          )}
          {mensagem && (
            <span className="text-[11px] text-muted">{mensagem}</span>
          )}
        </div>
      </form>
    </Card>
  );
}

function LimitesDeUso() {
  const [orcamento, setOrcamento] = useState<Orcamento | null>(null);
  const [mensagem, setMensagem] = useState<string | null>(null);

  useEffect(() => {
    api
      .get<Orcamento>("/ai-credits/orcamento")
      .then(setOrcamento)
      .catch(() => undefined);
  }, []);

  async function salvar(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const numero = (campo: string) =>
      form.get(campo) ? Number(form.get(campo)) : null;
    const modulos: Record<string, number> = {};
    for (const modulo of ["predator", "crm", "map", "bids"]) {
      const valor = numero(`modulo_${modulo}`);
      if (valor !== null) modulos[modulo] = valor / 100;
    }
    try {
      setOrcamento(
        await api.put<Orcamento>("/ai-credits/orcamento", {
          orcamento_mensal_creditos: numero("orcamento_mensal_creditos"),
          limite_diario_creditos: numero("limite_diario_creditos"),
          limite_usuario_creditos: numero("limite_usuario_creditos"),
          limite_api_creditos: numero("limite_api_creditos"),
          limites_modulo_percentual: Object.keys(modulos).length
            ? modulos
            : null,
          percentual_alerta: numero("percentual_alerta") ?? 80,
          parada_rigida: form.get("parada_rigida") === "on",
        }),
      );
      setMensagem("Limites salvos.");
    } catch (error) {
      setMensagem(
        error instanceof ApiError ? error.message : "Não foi possível salvar.",
      );
    }
  }

  if (!orcamento) return null;
  const modulo = (nome: string) => {
    const valor = orcamento.limites_modulo_percentual?.[nome];
    return valor === undefined ? "" : Math.round(valor * 100);
  };
  return (
    <Card>
      <SectionLabel>Limites de uso</SectionLabel>
      <form
        onSubmit={salvar}
        className="grid grid-cols-1 gap-2 text-[12px] sm:grid-cols-2"
      >
        <Input
          name="orcamento_mensal_creditos"
          type="number"
          min="1"
          defaultValue={orcamento.orcamento_mensal_creditos ?? ""}
          placeholder="Máximo por mês (créditos)"
        />
        <Input
          name="limite_diario_creditos"
          type="number"
          min="1"
          defaultValue={orcamento.limite_diario_creditos ?? ""}
          placeholder="Máximo por dia"
        />
        <Input
          name="limite_usuario_creditos"
          type="number"
          min="1"
          defaultValue={orcamento.limite_usuario_creditos ?? ""}
          placeholder="Máximo por usuário/mês"
        />
        <Input
          name="limite_api_creditos"
          type="number"
          min="1"
          defaultValue={orcamento.limite_api_creditos ?? ""}
          placeholder="Máximo via API/mês"
        />
        {["predator", "crm", "map", "bids"].map((nome) => (
          <Input
            key={nome}
            name={`modulo_${nome}`}
            type="number"
            min="1"
            max="100"
            defaultValue={modulo(nome)}
            placeholder={`${nome.toUpperCase()}: % máximo do mês`}
          />
        ))}
        <Input
          name="percentual_alerta"
          type="number"
          min="1"
          max="100"
          defaultValue={orcamento.percentual_alerta}
          placeholder="Avisar em (%)"
        />
        <label className="flex items-center gap-1.5">
          <input
            type="checkbox"
            name="parada_rigida"
            defaultChecked={orcamento.parada_rigida}
          />{" "}
          Bloquear ao atingir o limite
        </label>
        <div className="flex items-center gap-2 sm:col-span-2">
          <Button size="sm" type="submit">
            Salvar limites
          </Button>
          {mensagem && (
            <span className="text-[11px] text-muted">{mensagem}</span>
          )}
        </div>
      </form>
    </Card>
  );
}

export function AiCredits() {
  const { usuario } = useAuth();
  const admin = usuario?.papel === "admin" || usuario?.papel === "super_admin";
  const [carteira, setCarteira] = useState<Carteira | null>(null);
  const [consumo, setConsumo] = useState<Consumo | null>(null);
  const [compras, setCompras] = useState<Compra[]>([]);
  const [alertas, setAlertas] = useState<Alerta[]>([]);
  const [pacotes, setPacotes] = useState<Pacote[]>([]);
  const [erro, setErro] = useState<string | null>(null);

  const carregar = useCallback(async () => {
    try {
      const [carteiraResp, consumoResp] = await Promise.all([
        api.get<Carteira>("/ai-credits/carteira"),
        api.get<Consumo>("/ai-credits/consumo?dias=30"),
      ]);
      setCarteira(carteiraResp);
      setConsumo(consumoResp);
      if (admin) {
        const [comprasResp, alertasResp, pacotesResp] = await Promise.all([
          api.get<Compra[]>("/ai-credits/compras"),
          api.get<Alerta[]>("/ai-credits/alertas"),
          api.get<{ pacotes: Pacote[] }>("/ai-credits/pacotes"),
        ]);
        setCompras(comprasResp);
        setAlertas(alertasResp);
        setPacotes(pacotesResp.pacotes);
      }
    } catch {
      setErro("Não foi possível carregar os AI Credits.");
    }
  }, [admin]);

  useEffect(() => {
    carregar();
  }, [carregar]);

  async function pagar(compra: Compra) {
    try {
      const atualizada = await api.post<Compra>(
        `/ai-credits/compras/${compra.id}/checkout`,
      );
      if (atualizada.url_checkout)
        window.location.href = atualizada.url_checkout;
    } catch (error) {
      setErro(
        error instanceof ApiError
          ? error.message
          : "Não foi possível abrir o pagamento.",
      );
    }
  }

  if (!carteira)
    return (
      <div className="p-5.5 text-[12px] text-muted">
        {erro ?? "Carregando…"}
      </div>
    );

  return (
    <div className="p-5.5">
      <div className="mb-5 flex flex-wrap items-end justify-between gap-2">
        <div>
          <div className="font-head text-xl font-bold">AI Credits</div>
          <div className="mt-0.5 text-[11px] text-muted">
            Carteira compartilhada da empresa. Consome primeiro o que vence
            primeiro.{" "}
            <Link
              to="/como-funcionam-ai-credits"
              className="text-cyan hover:underline"
            >
              Como funcionam os AI Credits
            </Link>
          </div>
        </div>
        {carteira.modo === "MEASURE" && (
          <Badge tone="amber">Em medição: uso registrado sem bloqueio</Badge>
        )}
      </div>
      {erro && <div className="mb-4 text-[12px] text-red">{erro}</div>}

      <div className="mb-4 grid grid-cols-2 gap-2.5 sm:grid-cols-4">
        <KpiCard
          label="Disponível"
          value={creditos(carteira.disponivel)}
          sub={
            carteira.reservado
              ? `${creditos(carteira.reservado)} em uso agora`
              : undefined
          }
          colorClassName="text-green"
        />
        <KpiCard
          label="Incluídos no plano"
          value={creditos(carteira.incluido_no_plano)}
          sub={`${creditos(carteira.franquia_mensal)} por mês, não acumulam`}
        />
        <KpiCard
          label="Comprados"
          value={creditos(carteira.comprado)}
          sub="válidos por 12 meses"
        />
        <KpiCard
          label="Promocionais e ajustes"
          value={creditos(carteira.promocional + carteira.ajustes)}
          colorClassName="text-amber"
        />
      </div>

      <BarraUso uso={carteira.uso_do_mes} />

      {carteira.a_vencer_30_dias.length > 0 && (
        <Card className="mb-4">
          <SectionLabel>Vencem nos próximos 30 dias</SectionLabel>
          {carteira.a_vencer_30_dias.map((lote) => (
            <div
              key={`${lote.tipo}-${lote.expira_em}`}
              className="flex justify-between py-1 text-[12px]"
            >
              <span>{ROTULO_TIPO[lote.tipo] ?? lote.tipo}</span>
              <span className="text-muted">
                {creditos(lote.quantidade)} em {data(lote.expira_em)}
              </span>
            </div>
          ))}
        </Card>
      )}

      {admin && <ComprarPacotes aoComprar={() => carregar()} />}

      {consumo && (
        <div className="mb-4 grid grid-cols-1 gap-3.5 lg:grid-cols-3">
          <Tabela titulo="Por módulo (30 dias)" linhas={consumo.por_modulo} />
          <Tabela
            titulo="Operações que mais consomem"
            linhas={consumo.por_workload}
          />
          <Tabela titulo="Por agente" linhas={consumo.por_agente} />
        </div>
      )}

      {admin && (
        <>
          <div className="mb-4 grid grid-cols-1 gap-3.5 lg:grid-cols-2">
            <RecargaAutomatica pacotes={pacotes} />
            <LimitesDeUso />
          </div>
          <div className="grid grid-cols-1 gap-3.5 lg:grid-cols-2">
            <Card>
              <SectionLabel>Compras</SectionLabel>
              {compras.map((compra) => (
                <div
                  key={compra.id}
                  className="flex items-center justify-between border-b border-border py-1.5 text-[12px]"
                >
                  <span>
                    {compra.pacote} · {creditos(compra.creditos)} ·{" "}
                    {brl(compra.preco)}
                    {compra.origem === "AUTO_RECARGA" && (
                      <span className="text-muted"> (recarga automática)</span>
                    )}
                  </span>
                  {compra.status === "PENDENTE" ? (
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => pagar(compra)}
                    >
                      Pagar
                    </Button>
                  ) : (
                    <Badge
                      tone={compra.status === "APROVADA" ? "green" : "red"}
                    >
                      {compra.status}
                    </Badge>
                  )}
                </div>
              ))}
              {compras.length === 0 && (
                <div className="text-[12px] text-muted">
                  Nenhuma compra ainda.
                </div>
              )}
            </Card>
            <Card>
              <SectionLabel>Avisos de uso</SectionLabel>
              {alertas.map((alerta) => (
                <div
                  key={`${alerta.periodo}-${alerta.nivel}`}
                  className="flex justify-between py-1 text-[12px]"
                >
                  <span>
                    {alerta.periodo}: {alerta.nivel}% da cota do mês
                  </span>
                  <Badge tone={alerta.nivel >= 95 ? "red" : "amber"}>
                    {alerta.tipo}
                  </Badge>
                </div>
              ))}
              {alertas.length === 0 && (
                <div className="text-[12px] text-muted">
                  Nenhum aviso neste período.
                </div>
              )}
            </Card>
          </div>
        </>
      )}
    </div>
  );
}
