import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, SectionLabel } from "@/components/ui/Card";
import { Input, Select } from "@/components/ui/Input";
import { api, ApiError } from "@/lib/api";

interface Registro {
  id: number;
  [campo: string]: unknown;
}

interface Painel {
  valor_planejado: number;
  comprometido: number;
  contratado: number;
  executado: number;
  percentual_execucao: number | null;
  processos_atrasados: { processo_id: number; objeto: string }[];
  demandas_em_risco: { demanda_id: number; necessidade: string }[];
  proximas_contratacoes: {
    item_pca_id: number;
    descricao: string;
    data_prevista: string;
  }[];
}

interface Sinal {
  tipo: string;
  severidade: string;
  mensagem: string;
}

interface Acao {
  acao: string;
  motivo: string;
  severidade: string;
}

const TOM: Record<string, "red" | "amber" | "muted"> = {
  ALTA: "red",
  ATENCAO: "amber",
  INFO: "muted",
};

function moeda(valor: number): string {
  return valor.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

/** Public Procurement — Buy Side (Fase 10). Riscos são sinais analíticos
 * para revisão, nunca conclusão jurídica; aprovações são de administrador. */
export function ComprasPublicas() {
  const [orgaos, setOrgaos] = useState<Registro[]>([]);
  const [planos, setPlanos] = useState<Registro[]>([]);
  const [processos, setProcessos] = useState<Registro[]>([]);
  const [demandas, setDemandas] = useState<Registro[]>([]);
  const [planoId, setPlanoId] = useState<number | null>(null);
  const [painel, setPainel] = useState<Painel | null>(null);
  const [sinais, setSinais] = useState<{
    aviso: string;
    sinais: Sinal[];
    nao_avaliados: string[];
  } | null>(null);
  const [acoes, setAcoes] = useState<Acao[]>([]);
  const [erro, setErro] = useState<string | null>(null);

  const carregar = useCallback(async () => {
    try {
      const [o, p, pr, d, s, a] = await Promise.all([
        api.get<Registro[]>("/procurement/orgaos"),
        api.get<Registro[]>("/procurement/planos"),
        api.get<Registro[]>("/procurement/processos"),
        api.get<Registro[]>("/procurement/demandas"),
        api.get<{ aviso: string; sinais: Sinal[]; nao_avaliados: string[] }>(
          "/procurement/riscos",
        ),
        api.get<Acao[]>("/procurement/proximas-acoes"),
      ]);
      setOrgaos(o);
      setPlanos(p);
      setProcessos(pr);
      setDemandas(d);
      setSinais(s);
      setAcoes(a);
      setPlanoId((atual) => atual ?? (p[0]?.id as number | undefined) ?? null);
    } catch (error) {
      setErro(
        error instanceof ApiError
          ? error.message
          : "Não foi possível carregar compras.",
      );
    }
  }, []);

  useEffect(() => {
    carregar();
  }, [carregar]);

  useEffect(() => {
    if (planoId === null) return;
    api
      .get<Painel>(`/procurement/planos/${planoId}/painel`)
      .then(setPainel)
      .catch(() => setPainel(null));
  }, [planoId]);

  async function criar(
    recurso: string,
    corpo: Record<string, unknown>,
    formulario: HTMLFormElement,
  ) {
    try {
      await api.post(`/procurement/${recurso}`, corpo);
      formulario.reset();
      await carregar();
    } catch (error) {
      setErro(
        error instanceof ApiError ? error.message : "Não foi possível salvar.",
      );
    }
  }

  function novoOrgao(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    criar(
      "orgaos",
      {
        nome: String(form.get("nome")),
        cnpj: String(form.get("cnpj") ?? "") || null,
      },
      event.currentTarget,
    );
  }

  function novoPlano(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    criar(
      "planos",
      {
        orgao_id: Number(form.get("orgao_id")),
        ano: Number(form.get("ano")),
        nome: String(form.get("nome")),
      },
      event.currentTarget,
    );
  }

  function novoProcesso(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const valor = String(form.get("valor_estimado") ?? "");
    criar(
      "processos",
      {
        orgao_id: Number(form.get("orgao_id")),
        objeto: String(form.get("objeto")),
        valor_estimado: valor ? Number(valor) : null,
      },
      event.currentTarget,
    );
  }

  return (
    <div className="flex flex-col gap-4" data-testid="compras-publicas">
      <div>
        <div className="font-head text-xl font-bold">Compras públicas</div>
        <div className="text-[11px] text-muted">
          Planejamento, demandas, processos, contratos e fornecedores do órgão.
          Dados sigilosos do comprador: nunca aparecem para fornecedores nem na
          rede.
        </div>
      </div>
      {erro && <div className="text-[12px] text-red">{erro}</div>}

      <div className="grid grid-cols-1 gap-3.5 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <div className="flex items-center justify-between">
            <SectionLabel>Plano de contratações</SectionLabel>
            <Select
              value={planoId ?? ""}
              onChange={(e) => setPlanoId(Number(e.target.value))}
              className="w-48"
            >
              {planos.map((p) => (
                <option key={p.id} value={p.id}>
                  {String(p.nome)}
                </option>
              ))}
            </Select>
          </div>
          {painel ? (
            <div className="grid grid-cols-2 gap-2 text-[11px] sm:grid-cols-5">
              {(
                [
                  ["Planejado", painel.valor_planejado],
                  ["Comprometido", painel.comprometido],
                  ["Contratado", painel.contratado],
                  ["Executado", painel.executado],
                ] as [string, number][]
              ).map(([rotulo, valor]) => (
                <div key={rotulo}>
                  <div className="text-muted">{rotulo}</div>
                  <div className="font-bold text-text">{moeda(valor)}</div>
                </div>
              ))}
              <div>
                <div className="text-muted">Execução</div>
                <div className="font-bold text-text">
                  {painel.percentual_execucao === null
                    ? "—"
                    : `${Math.round(painel.percentual_execucao * 100)}%`}
                </div>
              </div>
              <div className="col-span-full text-muted">
                {painel.processos_atrasados.length} processo(s) atrasado(s) ·{" "}
                {painel.demandas_em_risco.length} demanda(s) em risco ·{" "}
                {painel.proximas_contratacoes.length} contratação(ões) nos
                próximos 90 dias
              </div>
            </div>
          ) : (
            <div className="text-[11px] text-muted">
              Cadastre um plano para ver o painel.
            </div>
          )}
          <form onSubmit={novoPlano} className="mt-3 flex flex-wrap gap-2">
            <Select name="orgao_id" required className="w-48">
              {orgaos.map((o) => (
                <option key={o.id} value={o.id}>
                  {String(o.nome)}
                </option>
              ))}
            </Select>
            <Input
              name="ano"
              type="number"
              required
              defaultValue={new Date().getFullYear()}
              className="w-24"
            />
            <Input
              name="nome"
              required
              placeholder="Nome do plano"
              className="flex-1"
            />
            <Button type="submit" size="sm" disabled={orgaos.length === 0}>
              Novo plano
            </Button>
          </form>
          <form onSubmit={novoOrgao} className="mt-2 flex flex-wrap gap-2">
            <Input
              name="nome"
              required
              placeholder="Órgão / entidade"
              className="flex-1"
            />
            <Input name="cnpj" placeholder="CNPJ" className="w-44" />
            <Button type="submit" size="sm">
              Novo órgão
            </Button>
          </form>
        </Card>

        <Card>
          <SectionLabel>Próximas ações sugeridas</SectionLabel>
          {acoes.length === 0 ? (
            <div className="text-[11px] text-muted">Nada pendente.</div>
          ) : (
            <div className="flex flex-col gap-1.5 text-[11px]">
              {acoes.map((a, indice) => (
                <div
                  key={indice}
                  className="rounded-md border border-border p-2"
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-text">{a.acao}</span>
                    <Badge tone={TOM[a.severidade] ?? "muted"}>
                      {a.severidade}
                    </Badge>
                  </div>
                  <div className="mt-0.5 text-muted">{a.motivo}</div>
                </div>
              ))}
            </div>
          )}
        </Card>

        <Card className="lg:col-span-2">
          <SectionLabel>Processos</SectionLabel>
          <div className="flex flex-col gap-1.5 text-[11px]">
            {processos.map((p) => (
              <Link
                key={p.id}
                to={`/compras/processos/${p.id}`}
                className="flex items-center justify-between rounded-md border border-border p-2 hover:border-cyan"
              >
                <span className="text-text">{String(p.objeto)}</span>
                <Badge tone="muted">{String(p.status)}</Badge>
              </Link>
            ))}
            {processos.length === 0 && (
              <div className="text-muted">Nenhum processo.</div>
            )}
          </div>
          <form onSubmit={novoProcesso} className="mt-3 flex flex-wrap gap-2">
            <Select name="orgao_id" required className="w-48">
              {orgaos.map((o) => (
                <option key={o.id} value={o.id}>
                  {String(o.nome)}
                </option>
              ))}
            </Select>
            <Input
              name="objeto"
              required
              placeholder="Objeto"
              className="flex-1"
            />
            <Input
              name="valor_estimado"
              type="number"
              min={0}
              placeholder="Valor estimado"
              className="w-40"
            />
            <Button type="submit" size="sm" disabled={orgaos.length === 0}>
              Novo processo
            </Button>
          </form>
          <div className="mt-2 text-[10px] text-muted">
            {demandas.length} demanda(s) registrada(s).
          </div>
        </Card>

        <Card>
          <SectionLabel>Sinais para revisão</SectionLabel>
          {sinais && (
            <div className="mb-1.5 text-[10px] text-muted">{sinais.aviso}</div>
          )}
          <div className="flex flex-col gap-1.5 text-[11px]">
            {sinais?.sinais.map((s, indice) => (
              <div
                key={indice}
                className="flex items-start justify-between gap-2"
              >
                <span className="text-text">{s.mensagem}</span>
                <Badge tone={TOM[s.severidade] ?? "muted"}>
                  {s.severidade}
                </Badge>
              </div>
            ))}
            {sinais?.nao_avaliados.map((n) => (
              <div key={n} className="text-[10px] text-muted">
                Não avaliado: {n}
              </div>
            ))}
          </div>
        </Card>
      </div>
    </div>
  );
}
