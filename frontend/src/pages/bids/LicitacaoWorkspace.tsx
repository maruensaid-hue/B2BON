import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Link, useParams } from "react-router-dom";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, SectionLabel } from "@/components/ui/Card";
import { Input, Select } from "@/components/ui/Input";
import { confirmarConsumo } from "@/lib/aiCredits";
import { api, ApiError, postFile } from "@/lib/api";
import { MODALIDADES, type Licitacao } from "@/pages/bids/tipos";

interface Documento {
  id: number;
  tipo: string;
  nome_arquivo: string;
  sha256: string;
  paginas: number;
  fonte: string;
  status_analise: string;
}

interface Requisito {
  id: number;
  documento_id: number | null;
  categoria: string;
  descricao: string;
  evidencia: string | null;
  pagina: number | null;
  clausula: string | null;
  obrigatorio: boolean | null;
  origem: string;
  status: string;
}

interface LinhaMatriz {
  requisito_id: number;
  categoria: string;
  requisito: string;
  status: string;
  status_calculado: string;
  motivo: string;
  risco: string | null;
  fonte: string | null;
  ajuste_manual: { justificativa: string } | null;
}

interface Fator {
  fator: string;
  status: string;
  motivo: string;
}

interface Workspace {
  licitacao: Licitacao & { objeto: string | null; concorrentes: string[] };
  documentos: Documento[];
  requisitos: Requisito[];
  matriz_conformidade: {
    linhas: LinhaMatriz[];
    contagem: Record<string, number>;
  };
  go_no_go: {
    recomendacao: string;
    motivo: string;
    fatores: Fator[];
    bloqueios: string[];
  };
  decisoes: {
    id: number;
    recomendacao: string;
    decisao: string;
    justificativa: string | null;
    criado_em: string;
  }[];
  prazos: { titulo: string; dias: number | null; nivel: string }[];
}

const TOM_CONFORMIDADE: Record<
  string,
  "green" | "amber" | "red" | "muted" | "violet"
> = {
  COMPLIANT: "green",
  PARTIALLY_COMPLIANT: "amber",
  NON_COMPLIANT: "red",
  UNKNOWN: "muted",
  REQUIRES_REVIEW: "violet",
};
const TOM_FATOR: Record<string, "green" | "amber" | "red" | "muted"> = {
  FAVORAVEL: "green",
  ATENCAO: "amber",
  DESFAVORAVEL: "red",
  UNKNOWN: "muted",
};

/** Bid Workspace (Fase 9). Cada requisito mostra de onde veio: documento,
 * página, cláusula e o trecho literal. */
export function LicitacaoWorkspace() {
  const { id } = useParams<{ id: string }>();
  const [ws, setWs] = useState<Workspace | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);
  const [ocupado, setOcupado] = useState(false);

  const carregar = useCallback(async () => {
    try {
      setWs(await api.get<Workspace>(`/bids/licitacoes/${id}/workspace`));
    } catch (error) {
      setErro(
        error instanceof ApiError
          ? error.message
          : "Não foi possível carregar a licitação.",
      );
    }
  }, [id]);

  useEffect(() => {
    carregar();
  }, [carregar]);

  async function executar(
    acao: () => Promise<unknown>,
    sucesso?: (resultado: unknown) => string,
  ) {
    setErro(null);
    setAviso(null);
    setOcupado(true);
    try {
      const resultado = await acao();
      if (sucesso) setAviso(sucesso(resultado));
      await carregar();
    } catch (error) {
      setErro(
        error instanceof ApiError
          ? error.message
          : "Não foi possível concluir a ação.",
      );
    } finally {
      setOcupado(false);
    }
  }

  function enviarDocumento(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formulario = event.currentTarget;
    const form = new FormData(formulario);
    const arquivo = form.get("arquivo") as File | null;
    if (!arquivo || arquivo.size === 0) return;
    executar(async () => {
      await postFile(`/bids/licitacoes/${id}/documentos`, arquivo, {
        tipo: String(form.get("tipo")),
      });
      formulario.reset();
    });
  }

  function decidir(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    executar(() =>
      api.post(`/bids/licitacoes/${id}/go-no-go`, {
        decisao: String(form.get("decisao")),
        justificativa: String(form.get("justificativa") ?? "") || null,
      }),
    );
  }

  if (!ws)
    return (
      <div className="text-[12px] text-muted">{erro ?? "Carregando..."}</div>
    );
  const lic = ws.licitacao;
  const nomeDocumento = (docId: number | null) =>
    ws.documentos.find((d) => d.id === docId)?.nome_arquivo ?? "manual";

  return (
    <div className="flex flex-col gap-3.5" data-testid="bid-workspace">
      <Link to="/bids" className="text-[11px] text-cyan">
        ← Licitações
      </Link>
      <div>
        <div className="font-head text-xl font-bold">{lic.titulo}</div>
        <div className="text-[11px] text-muted">
          {lic.orgao_nome ?? "Órgão não informado"} ·{" "}
          {MODALIDADES[lic.modalidade] ?? lic.modalidade} · fonte {lic.fonte}
          {lic.fonte_url && (
            <>
              {" "}
              ·{" "}
              <a
                href={lic.fonte_url}
                target="_blank"
                rel="noreferrer"
                className="text-cyan"
              >
                ver na fonte
              </a>
            </>
          )}{" "}
          · status <b>{lic.status}</b>
        </div>
      </div>
      {erro && <div className="text-[12px] text-red">{erro}</div>}
      {aviso && <div className="text-[12px] text-green">{aviso}</div>}

      <div className="grid grid-cols-1 gap-3.5 lg:grid-cols-2">
        <Card>
          <SectionLabel>Documentos</SectionLabel>
          <div className="flex flex-col gap-1.5 text-[11px]">
            {ws.documentos.map((d) => (
              <div
                key={d.id}
                className="flex items-center justify-between gap-2"
              >
                <span title={`SHA-256 ${d.sha256}`}>
                  <span className="text-text">{d.nome_arquivo}</span>
                  <span className="text-muted">
                    {" "}
                    · {d.tipo} · {d.paginas} pág. · {d.status_analise}
                  </span>
                </span>
                {d.status_analise !== "SEM_TEXTO" && (
                  <button
                    type="button"
                    disabled={ocupado}
                    className="text-cyan"
                    onClick={() =>
                      executar(
                        async () => {
                          const confirmar = await confirmarConsumo(
                            `/bids/documentos/${d.id}/estimativa`,
                          );
                          if (confirmar === null)
                            throw new ApiError(0, "Análise cancelada.");
                          return api.post(
                            `/bids/documentos/${d.id}/analisar?confirmar=${confirmar}`,
                          );
                        },
                        (r) => {
                          const res = r as {
                            sugeridos: number;
                            descartados_sem_evidencia: number;
                            analise_parcial: boolean;
                          };
                          return `${res.sugeridos} requisito(s) sugerido(s); ${res.descartados_sem_evidencia} descartado(s) por não estarem no texto${res.analise_parcial ? "; análise parcial (documento longo)" : ""}.`;
                        },
                      )
                    }
                  >
                    🧠 Analisar
                  </button>
                )}
              </div>
            ))}
            {ws.documentos.length === 0 && (
              <div className="text-muted">
                Envie o edital e o TR (PDF com texto ou .txt).
              </div>
            )}
          </div>
          <form
            onSubmit={enviarDocumento}
            className="mt-2 flex flex-wrap items-center gap-2"
          >
            <Select name="tipo" defaultValue="EDITAL" className="w-32">
              {[
                "EDITAL",
                "TR",
                "ANEXO",
                "ESCLARECIMENTO",
                "ATA",
                "CONTRATO",
                "OUTRO",
              ].map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </Select>
            <input
              name="arquivo"
              type="file"
              accept=".pdf,.txt,application/pdf,text/plain"
              className="text-[11px]"
            />
            <Button type="submit" size="sm" disabled={ocupado}>
              Enviar
            </Button>
          </form>
        </Card>

        <Card>
          <SectionLabel>Go / No-Go</SectionLabel>
          <div className="flex items-center gap-2 text-[12px]">
            Recomendação:
            <Badge
              tone={
                ws.go_no_go.recomendacao === "GO"
                  ? "green"
                  : ws.go_no_go.recomendacao === "NO_GO"
                    ? "red"
                    : "amber"
              }
            >
              {ws.go_no_go.recomendacao}
            </Badge>
          </div>
          <div className="mt-1 text-[11px] text-muted">
            {ws.go_no_go.motivo}
          </div>
          <div className="mt-2 flex flex-col gap-1 text-[11px]">
            {ws.go_no_go.fatores.map((f) => (
              <div
                key={f.fator}
                className="flex items-start justify-between gap-2"
              >
                <span>
                  <span className="text-text">{f.fator}</span>{" "}
                  <span className="text-muted">— {f.motivo}</span>
                </span>
                <Badge tone={TOM_FATOR[f.status] ?? "muted"}>{f.status}</Badge>
              </div>
            ))}
          </div>
          <form onSubmit={decidir} className="mt-3 flex flex-wrap gap-2">
            <Select name="decisao" defaultValue="GO" className="w-28">
              <option value="GO">GO</option>
              <option value="NO_GO">NO GO</option>
            </Select>
            <Input
              name="justificativa"
              placeholder="Justificativa (obrigatória se divergir)"
              className="flex-1"
            />
            <Button type="submit" size="sm" disabled={ocupado}>
              Registrar decisão
            </Button>
          </form>
          {ws.decisoes.map((d) => (
            <div key={d.id} className="mt-1 text-[10px] text-muted">
              {new Date(d.criado_em).toLocaleString("pt-BR")}: decidido{" "}
              {d.decisao} (recomendação {d.recomendacao})
              {d.justificativa ? ` — ${d.justificativa}` : ""}
            </div>
          ))}
        </Card>

        <Card className="lg:col-span-2">
          <SectionLabel>Requisitos extraídos</SectionLabel>
          <div className="flex flex-col gap-1.5">
            {ws.requisitos.map((r) => (
              <div
                key={r.id}
                className="rounded-md border border-border p-2 text-[11px]"
              >
                <div className="flex items-center justify-between gap-2">
                  <span>
                    <span className="text-muted">{r.categoria}:</span>{" "}
                    <span className="text-text">{r.descricao}</span>{" "}
                    {r.obrigatorio === true && (
                      <Badge tone="violet">Obrigatório</Badge>
                    )}
                    {r.obrigatorio === false && <Badge>Desejável</Badge>}
                  </span>
                  {r.status === "sugerido" ? (
                    <span className="flex gap-2">
                      <button
                        type="button"
                        className="text-green"
                        onClick={() =>
                          executar(() =>
                            api.patch(`/bids/requisitos/${r.id}`, {
                              status: "confirmado",
                            }),
                          )
                        }
                      >
                        Confirmar
                      </button>
                      <button
                        type="button"
                        className="text-red"
                        onClick={() =>
                          executar(() =>
                            api.patch(`/bids/requisitos/${r.id}`, {
                              status: "descartado",
                            }),
                          )
                        }
                      >
                        Descartar
                      </button>
                    </span>
                  ) : (
                    <Badge tone="green">Confirmado</Badge>
                  )}
                </div>
                {r.evidencia && (
                  <div className="mt-0.5 text-[10px] text-muted">
                    {nomeDocumento(r.documento_id)}, pág. {r.pagina ?? "—"}
                    {r.clausula ? `, cláusula ${r.clausula}` : ""}:{" "}
                    <i>“{r.evidencia}”</i>
                  </div>
                )}
              </div>
            ))}
            {ws.requisitos.length === 0 && (
              <div className="text-[11px] text-muted">
                Analise um documento para extrair requisitos.
              </div>
            )}
          </div>
        </Card>

        <Card className="lg:col-span-2">
          <SectionLabel>Matriz de conformidade</SectionLabel>
          <div className="mb-2 flex flex-wrap gap-1.5">
            {Object.entries(ws.matriz_conformidade.contagem).map(
              ([status, n]) => (
                <Badge key={status} tone={TOM_CONFORMIDADE[status]}>
                  {status}: {n}
                </Badge>
              ),
            )}
          </div>
          <div className="flex flex-col gap-1 text-[11px]">
            {ws.matriz_conformidade.linhas.map((l) => (
              <div
                key={l.requisito_id}
                className="flex items-start justify-between gap-2 border-b border-border py-1"
              >
                <span>
                  <span className="text-text">{l.requisito}</span>
                  <span className="text-muted">
                    {" "}
                    — {l.motivo}
                    {l.risco ? ` Risco: ${l.risco}` : ""}
                    {l.ajuste_manual
                      ? ` (ajuste manual: ${l.ajuste_manual.justificativa})`
                      : ""}
                  </span>
                </span>
                <Badge tone={TOM_CONFORMIDADE[l.status]}>{l.status}</Badge>
              </div>
            ))}
          </div>
        </Card>
      </div>
    </div>
  );
}
