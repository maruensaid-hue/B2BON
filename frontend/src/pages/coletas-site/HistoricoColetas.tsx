import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, SectionLabel } from "@/components/ui/Card";
import { Select } from "@/components/ui/Input";
import { api, ApiError } from "@/lib/api";

type Tom = "cyan" | "violet" | "green" | "amber" | "red" | "muted";

interface ColetaResumo {
  id: number;
  conta_id: number;
  conta_nome: string | null;
  dominio: string | null;
  disparo: "manual" | "fila" | "reprocesso";
  reprocesso_de_id: number | null;
  estado: string;
  iniciada_em: string;
  concluida_em: string | null;
  paginas: number;
  dominio_situacao: string | null;
  financeiro_estado: string | null;
  indicadores: number;
  erro: string | null;
  avisos: number;
  ultima_coleta_bem_sucedida_da_conta: string | null;
}

interface Indicador {
  id: number;
  nome: string;
  tipo: "publicado" | "derivado";
  valor: number;
  moeda: string;
  escala: string;
  valor_original: string;
  periodo: string | null;
  url_fonte: string;
  trecho: string;
  metodo_extracao: string;
  confianca: string;
  estado_validacao: string;
  formula: string | null;
  origens: string[];
}

interface Evidencia {
  tipo: string;
  detalhe: string;
  encontrada: boolean;
}

interface PaginaColetada {
  url: string;
  coletado_em: string | null;
  caracteres: number | null;
  previa: string | null;
}

interface ColetaDetalhe extends Omit<ColetaResumo, "avisos" | "indicadores" | "dominio_situacao" | "financeiro_estado"> {
  fontes: string[];
  resumo: string | null;
  avisos: string[];
  dominio_verificacao: {
    origem: string | null;
    situacao: string | null;
    pontuacao: number | null;
    evidencias: Evidencia[];
    limitacoes: string[];
    validado_por: string | null;
    validado_em: string | null;
    exige_validacao_manual: boolean;
  };
  financeiro: { estado: string | null; mensagem: string | null; indicadores: Indicador[] };
  paginas_coletadas: PaginaColetada[];
  observacao_paginas: string;
}

const ESTADOS: Record<string, { rotulo: string; tom: Tom }> = {
  concluida: { rotulo: "Concluída", tom: "green" },
  concluida_sem_ia: { rotulo: "Coletada · análise pendente", tom: "amber" },
  falhou: { rotulo: "Falhou", tom: "red" },
  em_andamento: { rotulo: "Em andamento", tom: "cyan" },
};

const SITUACOES_DOMINIO: Record<string, { rotulo: string; tom: Tom }> = {
  confirmado: { rotulo: "Domínio confirmado", tom: "green" },
  confirmado_manualmente: { rotulo: "Confirmado manualmente", tom: "green" },
  provavel: { rotulo: "Domínio provável", tom: "amber" },
  inconclusivo: { rotulo: "Domínio inconclusivo", tom: "amber" },
  divergente: { rotulo: "Domínio divergente", tom: "red" },
};

const DISPAROS: Record<string, string> = { manual: "Manual", fila: "Fila em lote", reprocesso: "Reprocesso" };

const ROTULOS_INDICADOR: Record<string, string> = {
  receita_liquida: "Receita líquida",
  receita_bruta: "Receita bruta",
  lucro_liquido: "Lucro líquido",
  ebitda: "EBITDA",
  divida_liquida: "Dívida líquida",
  margem_liquida_pct: "Margem líquida",
};

function formatarData(valor: string | null): string {
  if (!valor) return "—";
  const data = new Date(valor.endsWith("Z") || valor.includes("+") ? valor : `${valor}Z`);
  return data.toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" });
}

function formatarValor(indicador: Indicador): string {
  if (indicador.moeda === "%") return `${indicador.valor.toFixed(2).replace(".", ",")}%`;
  return new Intl.NumberFormat("pt-BR", { style: "currency", currency: indicador.moeda, notation: "compact", maximumFractionDigits: 2 }).format(
    indicador.valor,
  );
}

function linkSeguro(url: string): string | null {
  return /^https?:\/\//i.test(url) ? url : null;
}

export function HistoricoColetas() {
  const [parametros] = useSearchParams();
  const contaFiltro = parametros.get("conta");
  const [coletas, setColetas] = useState<ColetaResumo[]>([]);
  const [estado, setEstado] = useState("");
  const [carregando, setCarregando] = useState(true);
  const [selecionada, setSelecionada] = useState<ColetaDetalhe | null>(null);
  const [acao, setAcao] = useState<string | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);

  const carregar = useCallback(async () => {
    setCarregando(true);
    setErro(null);
    try {
      const consulta = new URLSearchParams();
      if (estado) consulta.set("estado", estado);
      if (contaFiltro) consulta.set("conta_id", contaFiltro);
      const sufixo = consulta.toString() ? `?${consulta.toString()}` : "";
      setColetas(await api.get<ColetaResumo[]>(`/coletas-site${sufixo}`));
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível carregar o histórico.");
    } finally {
      setCarregando(false);
    }
  }, [estado, contaFiltro]);

  useEffect(() => {
    void carregar();
  }, [carregar]);

  async function abrir(id: number) {
    setErro(null);
    setAviso(null);
    try {
      setSelecionada(await api.get<ColetaDetalhe>(`/coletas-site/${id}`));
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível abrir a coleta.");
    }
  }

  async function executar(nome: string, chamada: () => Promise<ColetaDetalhe>, sucesso: string) {
    setAcao(nome);
    setErro(null);
    setAviso(null);
    try {
      setSelecionada(await chamada());
      setAviso(sucesso);
      await carregar();
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "A ação não pôde ser concluída.");
      await carregar(); // uma falha também gera linha no histórico
    } finally {
      setAcao(null);
    }
  }

  const reprocessar = (id: number) =>
    executar("reprocessar", () => api.post<ColetaDetalhe>(`/coletas-site/${id}/reprocessar`), "Nova coleta gerada. A anterior foi mantida no histórico.");
  const confirmarDominio = (id: number) =>
    executar("confirmar", () => api.post<ColetaDetalhe>(`/coletas-site/${id}/confirmar-dominio`), "Domínio confirmado manualmente.");

  return (
    <div className="p-5.5">
      <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-[18px] font-bold">Histórico de coletas de site</h1>
          <p className="mt-1 max-w-2xl text-[12px] text-muted">
            Cada pesquisa no site institucional de uma empresa fica registrada aqui: o domínio analisado, como ele foi confirmado, as páginas lidas
            e os indicadores financeiros públicos encontrados, sempre com a fonte. A coleta funciona mesmo quando a IA está indisponível.
          </p>
        </div>
        <div className="w-52">
          <Select label="Estado" value={estado} onChange={(e) => setEstado(e.target.value)}>
            <option value="">Todos</option>
            <option value="concluida">Concluída</option>
            <option value="concluida_sem_ia">Coletada · análise pendente</option>
            <option value="falhou">Falhou</option>
          </Select>
        </div>
      </div>

      {erro && <p className="mb-3 rounded-lg border border-red/30 bg-red/10 p-2.5 text-[12px] text-red">{erro}</p>}
      {aviso && <p className="mb-3 rounded-lg border border-green/30 bg-green/10 p-2.5 text-[12px] text-green">{aviso}</p>}

      <div className="grid grid-cols-1 gap-3.5 xl:grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)]">
        <Card>
          <SectionLabel>Coletas {contaFiltro ? "da empresa" : "recentes"}</SectionLabel>
          {carregando ? (
            <p className="text-[12px] text-muted">Carregando…</p>
          ) : coletas.length === 0 ? (
            <p className="text-[12px] text-muted">
              Nenhuma coleta registrada ainda. Use “Enriquecer (site)” na ficha de uma empresa para gerar a primeira.
            </p>
          ) : (
            <ul className="flex flex-col gap-2">
              {coletas.map((coleta) => {
                const situacaoEstado = ESTADOS[coleta.estado] ?? { rotulo: coleta.estado, tom: "muted" as Tom };
                const situacaoDominio = coleta.dominio_situacao ? SITUACOES_DOMINIO[coleta.dominio_situacao] : null;
                return (
                  <li key={coleta.id}>
                    <button
                      type="button"
                      onClick={() => void abrir(coleta.id)}
                      aria-pressed={selecionada?.id === coleta.id}
                      className={`w-full rounded-xl border p-3 text-left transition-colors hover:border-cyan ${
                        selecionada?.id === coleta.id ? "border-cyan bg-cyan/5" : "border-border bg-surf2"
                      }`}
                    >
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <span className="text-[13px] font-bold">{coleta.conta_nome ?? `Conta ${coleta.conta_id}`}</span>
                        <Badge tone={situacaoEstado.tom}>{situacaoEstado.rotulo}</Badge>
                      </div>
                      <div className="mt-1 text-[11px] text-muted">
                        {coleta.dominio ?? "sem domínio"} · {formatarData(coleta.iniciada_em)} · {DISPAROS[coleta.disparo] ?? coleta.disparo} ·{" "}
                        {coleta.paginas} página(s) · {coleta.indicadores} indicador(es)
                      </div>
                      <div className="mt-1.5 flex flex-wrap gap-1.5">
                        {situacaoDominio && <Badge tone={situacaoDominio.tom}>{situacaoDominio.rotulo}</Badge>}
                        {coleta.avisos > 0 && <Badge tone="amber">{coleta.avisos} aviso(s)</Badge>}
                      </div>
                      {coleta.erro && <div className="mt-1.5 text-[11px] text-red">{coleta.erro}</div>}
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </Card>

        <Card>
          {!selecionada ? (
            <p className="text-[12px] text-muted">Selecione uma coleta para ver o domínio, as fontes e os indicadores.</p>
          ) : (
            <div className="flex flex-col gap-4">
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div>
                  <div className="text-[15px] font-bold">{selecionada.conta_nome ?? `Conta ${selecionada.conta_id}`}</div>
                  <div className="text-[11px] text-muted">
                    {selecionada.dominio ?? "sem domínio"} · iniciada {formatarData(selecionada.iniciada_em)} · concluída{" "}
                    {formatarData(selecionada.concluida_em)}
                  </div>
                  <div className="text-[11px] text-muted">
                    Última coleta bem-sucedida desta empresa: {formatarData(selecionada.ultima_coleta_bem_sucedida_da_conta)}
                    {selecionada.reprocesso_de_id ? ` · reprocesso da coleta #${selecionada.reprocesso_de_id}` : ""}
                  </div>
                </div>
                <Button size="sm" disabled={acao !== null || selecionada.estado === "em_andamento"} onClick={() => void reprocessar(selecionada.id)}>
                  {acao === "reprocessar" ? "Reprocessando…" : "↻ Reprocessar"}
                </Button>
              </div>

              {selecionada.erro && <p className="rounded-lg border border-amber/30 bg-amber/10 p-2.5 text-[12px] text-amber">{selecionada.erro}</p>}
              {selecionada.avisos.map((texto) => (
                <p key={texto} className="rounded-lg border border-amber/30 bg-amber/10 p-2.5 text-[12px] text-amber">
                  {texto}
                </p>
              ))}

              <section>
                <SectionLabel>Confirmação do domínio</SectionLabel>
                <div className="mb-2 flex flex-wrap items-center gap-2">
                  {selecionada.dominio_verificacao.situacao && (
                    <Badge tone={SITUACOES_DOMINIO[selecionada.dominio_verificacao.situacao]?.tom ?? "muted"}>
                      {SITUACOES_DOMINIO[selecionada.dominio_verificacao.situacao]?.rotulo ?? selecionada.dominio_verificacao.situacao}
                    </Badge>
                  )}
                  <span className="text-[11px] text-muted">
                    origem: {selecionada.dominio_verificacao.origem === "descoberto_busca" ? "descoberto por busca na web" : "cadastrado na conta"}
                    {selecionada.dominio_verificacao.pontuacao !== null ? ` · pontuação ${selecionada.dominio_verificacao.pontuacao}` : ""}
                  </span>
                </div>
                <ul className="flex flex-col gap-1 text-[12px]">
                  {selecionada.dominio_verificacao.evidencias.map((ev) => (
                    <li key={`${ev.tipo}-${ev.detalhe}`} className={ev.encontrada ? "text-text" : "text-muted"}>
                      {ev.encontrada ? "✔" : "✘"} {ev.detalhe}
                    </li>
                  ))}
                  {selecionada.dominio_verificacao.limitacoes.map((limitacao) => (
                    <li key={limitacao} className="text-muted">
                      ℹ {limitacao}
                    </li>
                  ))}
                </ul>
                {selecionada.dominio_verificacao.validado_por && (
                  <p className="mt-1 text-[11px] text-muted">
                    Validado manualmente em {formatarData(selecionada.dominio_verificacao.validado_em)}.
                  </p>
                )}
                {selecionada.dominio_verificacao.exige_validacao_manual && (
                  <Button className="mt-2" size="sm" variant="ghost" disabled={acao !== null} onClick={() => void confirmarDominio(selecionada.id)}>
                    {acao === "confirmar" ? "Confirmando…" : "Confirmar que este é o site da empresa"}
                  </Button>
                )}
              </section>

              <section>
                <SectionLabel>Indicadores financeiros públicos</SectionLabel>
                {selecionada.financeiro.indicadores.length === 0 ? (
                  <p className="text-[12px] text-muted">{selecionada.financeiro.mensagem ?? "Sem indicadores nesta coleta."}</p>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full text-left text-[12px]">
                      <thead className="text-[10px] tracking-wide text-muted uppercase">
                        <tr>
                          <th className="py-1 pr-3">Indicador</th>
                          <th className="py-1 pr-3">Valor</th>
                          <th className="py-1 pr-3">Período</th>
                          <th className="py-1 pr-3">Origem</th>
                          <th className="py-1">Confiança</th>
                        </tr>
                      </thead>
                      <tbody>
                        {selecionada.financeiro.indicadores.map((ind) => {
                          const link = linkSeguro(ind.url_fonte);
                          return (
                            <tr key={ind.id} className="border-t border-border align-top">
                              <td className="py-1.5 pr-3 font-bold">{ROTULOS_INDICADOR[ind.nome] ?? ind.nome}</td>
                              <td className="py-1.5 pr-3">
                                {formatarValor(ind)}
                                <div className="text-[10px] text-muted">como escrito: {ind.valor_original}</div>
                              </td>
                              <td className="py-1.5 pr-3">{ind.periodo ?? <span className="text-muted">não identificado</span>}</td>
                              <td className="py-1.5 pr-3">
                                <Badge tone={ind.tipo === "derivado" ? "violet" : "cyan"}>{ind.tipo}</Badge>
                                <div className="mt-0.5 break-all text-[10px] text-muted">
                                  {link ? (
                                    <a href={link} target="_blank" rel="noopener noreferrer" className="text-cyan hover:underline">
                                      {ind.url_fonte}
                                    </a>
                                  ) : (
                                    ind.url_fonte
                                  )}
                                </div>
                                {ind.formula && <div className="text-[10px] text-muted">fórmula: {ind.formula}</div>}
                                <div className="text-[10px] text-muted">“…{ind.trecho}…”</div>
                              </td>
                              <td className="py-1.5">
                                <Badge tone={ind.confianca === "alta" ? "green" : "amber"}>{ind.confianca}</Badge>
                                <div className="text-[10px] text-muted">{ind.estado_validacao.replace(/_/g, " ")}</div>
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                )}
              </section>

              <section>
                <SectionLabel>Páginas consultadas ({selecionada.paginas_coletadas.length})</SectionLabel>
                <ul className="flex flex-col gap-1.5">
                  {selecionada.paginas_coletadas.map((pagina) => {
                    const link = linkSeguro(pagina.url);
                    return (
                      <li key={pagina.url}>
                        <details className="rounded-lg border border-border bg-surf2 p-2">
                          <summary className="cursor-pointer text-[12px] break-all">
                            {link ? (
                              <a href={link} target="_blank" rel="noopener noreferrer" className="text-cyan hover:underline">
                                {pagina.url}
                              </a>
                            ) : (
                              pagina.url
                            )}
                          </summary>
                          <p className="mt-1.5 text-[11px] whitespace-pre-line text-muted">
                            {pagina.previa ? `${pagina.previa}${(pagina.caracteres ?? 0) > pagina.previa.length ? "…" : ""}` : "Conteúdo não disponível."}
                          </p>
                        </details>
                      </li>
                    );
                  })}
                </ul>
                <p className="mt-1.5 text-[10px] text-muted">{selecionada.observacao_paginas}</p>
              </section>

              {selecionada.resumo && (
                <section>
                  <SectionLabel>Resumo da análise por IA</SectionLabel>
                  <p className="text-[12px] whitespace-pre-line">{selecionada.resumo}</p>
                  <p className="mt-1 text-[10px] text-muted">Interpretação gerada por IA a partir do texto coletado; confira nas fontes acima.</p>
                </section>
              )}
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}
