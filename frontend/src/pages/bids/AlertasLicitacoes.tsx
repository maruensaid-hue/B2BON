import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, SectionLabel } from "@/components/ui/Card";
import { Input, Select } from "@/components/ui/Input";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";

interface Fator {
  fator: string;
  pontos: number;
  maximo: number;
  detalhe: string;
}

interface Edital {
  titulo: string;
  orgao_nome: string | null;
  uf: string | null;
  municipio: string | null;
  valor_estimado: number | null;
  prazo_proposta: string | null;
  situacao_externa: string | null;
  url: string | null;
}

interface Alerta {
  id: number;
  score: number;
  fatores: Fator[];
  regras: { id: number; nome: string }[];
  motivo: "nova" | "atualizada";
  estado: "novo" | "visto" | "dispensado" | "acompanhado";
  atualizacao_nao_vista: boolean;
  situacao_externa: string | null;
  edital: Edital | null;
}

interface Regra {
  id: number;
  nome: string;
  ativa: boolean;
  icp_id: number | null;
  palavras_chave: string[];
  palavras_excluir: string[];
  ufs: string[];
  modalidades: string[];
  valor_minimo: number | null;
  valor_maximo: number | null;
  dias_minimos_prazo: number | null;
  usar_portfolio: boolean;
  relevancia_minima: number;
  frequencia: "imediata" | "diaria";
}

interface Resumo {
  por_estado: Record<string, number>;
  atualizacoes_nao_vistas: number;
  regras_ativas: number;
}

interface IcpResumo {
  id: number;
  nome: string;
}

const SITUACOES_DE_ATENCAO = ["revogad", "anulad", "suspens", "cancelad"];
const ROTULO_FATOR: Record<string, string> = {
  palavras_chave: "Palavras",
  uf: "UF",
  valor: "Valor",
  modalidade: "Modalidade",
  prazo: "Prazo",
};

function exigeAtencao(situacao: string | null): boolean {
  return !!situacao && SITUACOES_DE_ATENCAO.some((p) => situacao.toLowerCase().startsWith(p));
}

function dinheiro(valor: number | null): string {
  return valor == null ? "—" : valor.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

function dia(valor: string | null): string {
  return valor ? new Date(valor).toLocaleDateString("pt-BR") : "—";
}

function lista(texto: string): string[] {
  return texto
    .split(/[,;\n]/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function numero(texto: string): number | null {
  const limpo = texto.trim().replace(/\./g, "").replace(",", ".");
  return limpo === "" || Number.isNaN(Number(limpo)) ? null : Number(limpo);
}

const REGRA_VAZIA = {
  nome: "",
  palavras: "",
  excluir: "",
  ufs: "",
  valorMin: "",
  valorMax: "",
  relevancia: "40",
  frequencia: "diaria",
  portfolio: false,
  icp: "",
};

/** Alertas de oportunidades de licitação (V5.2.1): regras por tenant/ICP e a lista de editais compatíveis, com fatores explicáveis e link para a
 * fonte oficial. A compatibilidade mede o quanto o edital atende às regras — não é elegibilidade nem chance de vitória. */
export function AlertasLicitacoes() {
  const { usuario } = useAuth();
  const navegar = useNavigate();
  const ehAdmin = usuario?.papel === "admin" || usuario?.papel === "super_admin";
  const [alertas, setAlertas] = useState<Alerta[]>([]);
  const [regras, setRegras] = useState<Regra[]>([]);
  const [resumo, setResumo] = useState<Resumo | null>(null);
  const [icps, setIcps] = useState<IcpResumo[]>([]);
  const [estado, setEstado] = useState("");
  const [scoreMinimo, setScoreMinimo] = useState("");
  const [regraFiltro, setRegraFiltro] = useState("");
  const [erro, setErro] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);
  const [form, setForm] = useState(REGRA_VAZIA);
  const [salvando, setSalvando] = useState(false);

  const carregar = useCallback(async () => {
    try {
      const parametros = new URLSearchParams();
      if (estado) parametros.set("estado", estado);
      if (scoreMinimo) parametros.set("score_minimo", scoreMinimo);
      if (regraFiltro) parametros.set("regra_id", regraFiltro);
      const consulta = parametros.toString();
      const [a, r, s] = await Promise.all([
        api.get<Alerta[]>(`/bids/alertas${consulta ? `?${consulta}` : ""}`),
        api.get<Regra[]>("/bids/alertas/regras"),
        api.get<Resumo>("/bids/alertas/resumo"),
      ]);
      setAlertas(a);
      setRegras(r);
      setResumo(s);
      setErro(null);
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível carregar os alertas.");
    }
  }, [estado, scoreMinimo, regraFiltro]);

  useEffect(() => {
    carregar();
  }, [carregar]);

  useEffect(() => {
    api
      .get<IcpResumo[]>("/icp")
      .then(setIcps)
      .catch(() => setIcps([]));
  }, []);

  async function acao(id: number, tipo: "visto" | "dispensar" | "acompanhar") {
    try {
      const resposta = await api.post<{ licitacao?: { id: number } }>(`/bids/alertas/${id}/${tipo}`);
      if (tipo === "acompanhar" && resposta.licitacao) {
        navegar(`/bids/${resposta.licitacao.id}`);
        return;
      }
      await carregar();
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível concluir a ação.");
    }
  }

  async function criarRegra(evento: FormEvent) {
    evento.preventDefault();
    setSalvando(true);
    setErro(null);
    try {
      await api.post("/bids/alertas/regras", {
        nome: form.nome,
        palavras_chave: lista(form.palavras),
        palavras_excluir: lista(form.excluir),
        ufs: lista(form.ufs).map((u) => u.toUpperCase()),
        valor_minimo: numero(form.valorMin),
        valor_maximo: numero(form.valorMax),
        relevancia_minima: Number(form.relevancia) || 0,
        frequencia: form.frequencia,
        usar_portfolio: form.portfolio,
        icp_id: form.icp ? Number(form.icp) : null,
      });
      setForm(REGRA_VAZIA);
      setAviso("Regra criada. Os editais já coletados foram reavaliados.");
      await api.post("/bids/alertas/avaliar");
      await carregar();
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível criar a regra.");
    } finally {
      setSalvando(false);
    }
  }

  async function alternarRegra(regra: Regra) {
    try {
      await api.put(`/bids/alertas/regras/${regra.id}`, { ativa: !regra.ativa });
      await carregar();
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível alterar a regra.");
    }
  }

  async function excluirRegra(regra: Regra) {
    if (!window.confirm(`Excluir a regra "${regra.nome}"? Os alertas já gerados continuam na lista.`)) return;
    try {
      await api.delete(`/bids/alertas/regras/${regra.id}`);
      await carregar();
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível excluir a regra.");
    }
  }

  async function reavaliar() {
    try {
      const r = await api.post<{ criados: number; atualizados: number }>("/bids/alertas/avaliar");
      setAviso(`Avaliação concluída: ${r.criados} novo(s), ${r.atualizados} atualizado(s).`);
      await carregar();
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível avaliar agora.");
    }
  }

  return (
    <div className="space-y-4 p-5.5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h1 className="text-[18px] font-bold">Alertas de oportunidades</h1>
          <p className="max-w-3xl text-[12px] text-muted">
            Editais públicos que atendem às suas regras. A compatibilidade mostra quanto o edital cumpre os critérios que você definiu; não
            indica elegibilidade nem chance de vitória. Confira sempre o edital na fonte oficial.
          </p>
        </div>
        <Link to="/bids" className="text-[12px] text-cyan hover:underline">
          ← Licitações
        </Link>
      </div>

      {erro && <p className="rounded-lg border border-red/30 bg-red/10 p-2.5 text-[12px] text-red">{erro}</p>}
      {aviso && <p className="rounded-lg border border-green/30 bg-green/10 p-2.5 text-[12px] text-green">{aviso}</p>}

      {resumo && (
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          {[
            ["Novos", resumo.por_estado.novo ?? 0],
            ["Atualizados na fonte", resumo.atualizacoes_nao_vistas],
            ["Acompanhando", resumo.por_estado.acompanhado ?? 0],
            ["Regras ativas", resumo.regras_ativas],
          ].map(([rotulo, valor]) => (
            <Card key={String(rotulo)}>
              <SectionLabel>{rotulo}</SectionLabel>
              <div className="text-[22px] font-bold">{valor}</div>
            </Card>
          ))}
        </div>
      )}

      <Card>
        <SectionLabel>Oportunidades</SectionLabel>
        <div className="mb-3 grid grid-cols-1 gap-2 md:grid-cols-4">
          <Select label="Situação do alerta" value={estado} onChange={(e) => setEstado(e.target.value)}>
            <option value="">Todos</option>
            <option value="novo">Novos</option>
            <option value="visto">Vistos</option>
            <option value="acompanhado">Acompanhando</option>
            <option value="dispensado">Dispensados</option>
          </Select>
          <Input label="Compatibilidade mínima (%)" inputMode="numeric" value={scoreMinimo} onChange={(e) => setScoreMinimo(e.target.value.replace(/\D/g, ""))} />
          <Select label="Regra" value={regraFiltro} onChange={(e) => setRegraFiltro(e.target.value)}>
            <option value="">Todas</option>
            {regras.map((r) => (
              <option key={r.id} value={r.id}>
                {r.nome}
              </option>
            ))}
          </Select>
          {ehAdmin && (
            <div className="flex items-end">
              <Button variant="ghost" size="sm" type="button" onClick={reavaliar}>
                Reavaliar agora
              </Button>
            </div>
          )}
        </div>

        {alertas.length === 0 ? (
          <p className="text-[12px] text-muted">
            Nenhum alerta {estado || scoreMinimo || regraFiltro ? "com esses filtros" : "ainda"}. Crie uma regra abaixo; os editais entram quando a
            coleta de fontes públicas os encontra.
          </p>
        ) : (
          <ul className="space-y-2.5">
            {alertas.map((a) => {
              const e = a.edital;
              const atencao = exigeAtencao(a.situacao_externa);
              return (
                <li key={a.id} className="rounded-xl border border-border bg-surf2 p-3.5">
                  <div className="flex flex-wrap items-start justify-between gap-2">
                    <div className="min-w-0 flex-1">
                      <div className="text-[13px] font-bold">{e?.titulo ?? "Edital indisponível"}</div>
                      <div className="text-[11.5px] text-muted">
                        {e?.orgao_nome ?? "Órgão não informado"}
                        {e && (e.municipio || e.uf) ? ` · ${[e.municipio, e.uf].filter(Boolean).join(" / ")}` : ""} · {dinheiro(e?.valor_estimado ?? null)} · proposta até{" "}
                        {dia(e?.prazo_proposta ?? null)}
                      </div>
                    </div>
                    <div className="flex flex-wrap items-center gap-1.5">
                      {a.atualizacao_nao_vista && <Badge tone="amber">Atualizado na fonte</Badge>}
                      {a.situacao_externa && <Badge tone={atencao ? "red" : "muted"}>{a.situacao_externa}</Badge>}
                      <Badge tone={a.score >= 75 ? "green" : a.score >= 50 ? "cyan" : "muted"}>{a.score}% compatível</Badge>
                      <Badge tone={a.estado === "novo" ? "violet" : "muted"}>{a.estado}</Badge>
                    </div>
                  </div>
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {a.fatores.map((f) => (
                      <span key={f.fator} title={f.detalhe} className="rounded-md border border-border px-1.5 py-0.5 text-[10.5px] text-muted">
                        {ROTULO_FATOR[f.fator] ?? f.fator} {f.pontos}/{f.maximo} — {f.detalhe}
                      </span>
                    ))}
                  </div>
                  <div className="mt-2.5 flex flex-wrap items-center gap-2">
                    {e?.url && (
                      <a href={e.url} target="_blank" rel="noopener noreferrer" className="text-[11.5px] text-cyan hover:underline">
                        Ver na fonte oficial ↗
                      </a>
                    )}
                    <span className="text-[10.5px] text-muted">Regra: {a.regras.map((r) => r.nome).join(", ")}</span>
                    <span className="ml-auto flex gap-1.5">
                      {a.estado === "novo" && (
                        <Button size="sm" variant="ghost" type="button" onClick={() => acao(a.id, "visto")}>
                          Marcar como visto
                        </Button>
                      )}
                      {a.atualizacao_nao_vista && a.estado !== "novo" && (
                        <Button size="sm" variant="ghost" type="button" onClick={() => acao(a.id, "visto")}>
                          Li a atualização
                        </Button>
                      )}
                      {a.estado !== "dispensado" && a.estado !== "acompanhado" && (
                        <Button size="sm" variant="ghost" type="button" onClick={() => acao(a.id, "dispensar")}>
                          Dispensar
                        </Button>
                      )}
                      {a.estado !== "acompanhado" && (
                        <Button size="sm" type="button" onClick={() => acao(a.id, "acompanhar")}>
                          Acompanhar
                        </Button>
                      )}
                    </span>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </Card>

      <Card>
        <SectionLabel>Regras de alerta</SectionLabel>
        {regras.length === 0 ? (
          <p className="text-[12px] text-muted">Nenhuma regra ainda. {ehAdmin ? "Crie a primeira abaixo." : "Peça a um administrador para criar."}</p>
        ) : (
          <ul className="mb-3 space-y-2">
            {regras.map((r) => (
              <li key={r.id} className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-border p-2.5 text-[12px]">
                <div>
                  <b>{r.nome}</b> {r.ativa ? <Badge tone="green">ativa</Badge> : <Badge tone="muted">pausada</Badge>}
                  <div className="text-[11px] text-muted">
                    {r.palavras_chave.length > 0 && <>Palavras: {r.palavras_chave.join(", ")} · </>}
                    {r.usar_portfolio && <>Portfólio · </>}
                    {r.ufs.length > 0 && <>UF: {r.ufs.join(", ")} · </>}
                    {r.icp_id && !r.ufs.length && <>UFs do ICP · </>}
                    {(r.valor_minimo != null || r.valor_maximo != null) && <>Valor {dinheiro(r.valor_minimo)}–{dinheiro(r.valor_maximo)} · </>}
                    Mín. {r.relevancia_minima}% · {r.frequencia === "imediata" ? "a cada coleta" : "resumo diário"}
                  </div>
                </div>
                {ehAdmin && (
                  <div className="flex gap-1.5">
                    <Button size="sm" variant="ghost" type="button" onClick={() => alternarRegra(r)}>
                      {r.ativa ? "Pausar" : "Ativar"}
                    </Button>
                    <Button size="sm" variant="danger" type="button" onClick={() => excluirRegra(r)}>
                      Excluir
                    </Button>
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}

        {ehAdmin && (
          <form onSubmit={criarRegra} className="grid grid-cols-1 gap-2 md:grid-cols-2">
            <Input label="Nome da regra" required maxLength={80} value={form.nome} onChange={(e) => setForm({ ...form, nome: e.target.value })} />
            <Input
              label="Palavras-chave (separe por vírgula)"
              value={form.palavras}
              onChange={(e) => setForm({ ...form, palavras: e.target.value })}
              placeholder="software, licenças, segurança da informação"
            />
            <Input label="Excluir se citar (opcional)" value={form.excluir} onChange={(e) => setForm({ ...form, excluir: e.target.value })} />
            <Input label="UFs (ex.: SP, RJ)" value={form.ufs} onChange={(e) => setForm({ ...form, ufs: e.target.value })} />
            <Input label="Valor mínimo (R$)" inputMode="decimal" value={form.valorMin} onChange={(e) => setForm({ ...form, valorMin: e.target.value })} />
            <Input label="Valor máximo (R$)" inputMode="decimal" value={form.valorMax} onChange={(e) => setForm({ ...form, valorMax: e.target.value })} />
            <Select label="ICP (herda as UFs se você não informar)" value={form.icp} onChange={(e) => setForm({ ...form, icp: e.target.value })}>
              <option value="">Nenhum</option>
              {icps.map((i) => (
                <option key={i.id} value={i.id}>
                  {i.nome}
                </option>
              ))}
            </Select>
            <Input label="Compatibilidade mínima (%)" inputMode="numeric" value={form.relevancia} onChange={(e) => setForm({ ...form, relevancia: e.target.value.replace(/\D/g, "") })} />
            <Select label="Frequência" value={form.frequencia} onChange={(e) => setForm({ ...form, frequencia: e.target.value })}>
              <option value="diaria">Resumo diário</option>
              <option value="imediata">A cada coleta</option>
            </Select>
            <label className="flex items-center gap-2 self-end pb-2 text-[12px]">
              <input type="checkbox" checked={form.portfolio} onChange={(e) => setForm({ ...form, portfolio: e.target.checked })} />
              Usar também as palavras do nome da minha oferta ativa
            </label>
            <div className="md:col-span-2">
              <Button type="submit" disabled={salvando}>
                {salvando ? "Salvando…" : "Criar regra"}
              </Button>
            </div>
          </form>
        )}
      </Card>
    </div>
  );
}
