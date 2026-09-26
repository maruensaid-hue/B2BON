import { useCallback, useEffect, useState, type FormEvent } from "react";
import { useParams } from "react-router-dom";

import { ProcessWorkspace } from "@/components/sourcing/ProcessWorkspace";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, SectionLabel } from "@/components/ui/Card";
import { Input, Select } from "@/components/ui/Input";
import { confirmarConsumo } from "@/lib/aiCredits";
import { api, ApiError, postFile } from "@/lib/api";
import { PropostaAba } from "@/pages/bids/PropostaAba";
import { MODALIDADES, ROTULO_STATUS, type Licitacao } from "@/pages/bids/tipos";

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
  resposta: string | null;
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

interface Fluxo {
  codigo: string;
  segmento: string;
  tipo_processo: string;
  proximos_status: string[];
  aceita_resultado: boolean;
  final: boolean;
}

interface Workspace {
  licitacao: Licitacao & { objeto: string | null; concorrentes: string[] };
  fluxo: Fluxo;
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

  function registrarResultado(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const valor = String(form.get("valor_proposta") ?? "");
    executar(() =>
      api.post(`/bids/licitacoes/${id}/resultado`, {
        ganhou: form.get("ganhou") === "sim",
        vencedor: String(form.get("vencedor") ?? "") || null,
        valor_proposta: valor ? Number(valor) : null,
        motivo: String(form.get("motivo") ?? "") || null,
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

  const fluxo = ws.fluxo;
  const empresa = fluxo.segmento === "ENTERPRISE";
  const sugeridos = ws.requisitos.filter((r) => r.status === "sugerido").length;
  const andamento = (
    <Card>
      <SectionLabel>Andamento</SectionLabel>
      <div className="text-[11px] text-muted">
        Status atual{" "}
        <b className="text-text">{ROTULO_STATUS[lic.status] ?? lic.status}</b> ·
        fluxo {fluxo.codigo}
      </div>
      {fluxo.proximos_status.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-2">
          {fluxo.proximos_status.map((status) => (
            <Button
              key={status}
              size="sm"
              variant="ghost"
              disabled={ocupado}
              onClick={() =>
                executar(() =>
                  api.post(`/bids/licitacoes/${id}/status`, { status }),
                )
              }
            >
              {ROTULO_STATUS[status] ?? status}
            </Button>
          ))}
        </div>
      )}
      {fluxo.aceita_resultado && (
        <form
          onSubmit={registrarResultado}
          className="mt-3 flex flex-wrap gap-2"
        >
          <Select name="ganhou" defaultValue="sim" className="w-28">
            <option value="sim">Ganhamos</option>
            <option value="nao">Perdemos</option>
          </Select>
          <Input name="vencedor" placeholder="Vencedor" className="w-40" />
          <Input
            name="valor_proposta"
            type="number"
            step="0.01"
            placeholder="Valor da proposta"
            className="w-36"
          />
          <Input name="motivo" placeholder="Motivo" className="flex-1" />
          <Button type="submit" size="sm" disabled={ocupado}>
            Registrar resultado
          </Button>
        </form>
      )}
      {ws.prazos.length > 0 && (
        <div className="mt-3 flex flex-col gap-0.5 text-[11px]">
          {ws.prazos.map((p) => (
            <div key={p.titulo} className="text-muted">
              {p.titulo}: {p.dias === null ? "sem data" : `${p.dias} dia(s)`}
            </div>
          ))}
        </div>
      )}
    </Card>
  );
  const documentosCard = (
    <Card>
      <SectionLabel>Documentos</SectionLabel>
      <div className="flex flex-col gap-1.5 text-[11px]">
        {ws.documentos.map((d) => (
          <div key={d.id} className="flex items-center justify-between gap-2">
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
  );
  const goNoGoCard = (
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
      <div className="mt-1 text-[11px] text-muted">{ws.go_no_go.motivo}</div>
      <div className="mt-2 flex flex-col gap-1 text-[11px]">
        {ws.go_no_go.fatores.map((f) => (
          <div key={f.fator} className="flex items-start justify-between gap-2">
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
          {new Date(d.criado_em).toLocaleString("pt-BR")}: decidido {d.decisao}{" "}
          (recomendação {d.recomendacao})
          {d.justificativa ? ` — ${d.justificativa}` : ""}
        </div>
      ))}
    </Card>
  );
  const requisitosCard = (
    <Card>
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
            {r.status !== "descartado" && (
              <form
                className="mt-1 flex gap-2"
                onSubmit={(event) => {
                  event.preventDefault();
                  const form = new FormData(event.currentTarget);
                  executar(() =>
                    api.put(`/bids/requisitos/${r.id}/resposta`, {
                      resposta: String(form.get("resposta") ?? ""),
                    }),
                  );
                }}
              >
                <Input
                  name="resposta"
                  defaultValue={r.resposta ?? ""}
                  placeholder={
                    r.categoria === "PERGUNTA"
                      ? "Resposta à pergunta"
                      : "Como atendemos (entra na proposta)"
                  }
                  className="flex-1"
                />
                <Button
                  type="submit"
                  size="sm"
                  variant="ghost"
                  disabled={ocupado}
                >
                  Salvar
                </Button>
              </form>
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
  );
  const matrizCard = (
    <Card>
      <SectionLabel>Matriz de conformidade</SectionLabel>
      <div className="mb-2 flex flex-wrap gap-1.5">
        {Object.entries(ws.matriz_conformidade.contagem).map(([status, n]) => (
          <Badge key={status} tone={TOM_CONFORMIDADE[status]}>
            {status}: {n}
          </Badge>
        ))}
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
  );

  return (
    <ProcessWorkspace
      testId="bid-workspace"
      voltar={{ para: "/bids", rotulo: "Licitações" }}
      titulo={lic.titulo}
      subtitulo={
        <>
          {lic.orgao_nome ??
            (empresa ? "Emissor não informado" : "Órgão não informado")}{" "}
          · {MODALIDADES[lic.modalidade] ?? lic.modalidade} · fonte {lic.fonte}
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
          · status <b>{ROTULO_STATUS[lic.status] ?? lic.status}</b>
        </>
      }
      avisos={
        <>
          {erro && <div className="text-[12px] text-red">{erro}</div>}
          {aviso && <div className="text-[12px] text-green">{aviso}</div>}
        </>
      }
      abas={[
        {
          id: "visao",
          rotulo: "Visão geral",
          conteudo: (
            <div className="grid grid-cols-1 gap-3.5 lg:grid-cols-2">
              {andamento}
              {goNoGoCard}
            </div>
          ),
        },
        { id: "documentos", rotulo: "Documentos", conteudo: documentosCard },
        {
          id: "requisitos",
          rotulo: "Requisitos",
          conteudo: requisitosCard,
          contador: sugeridos,
        },
        { id: "conformidade", rotulo: "Conformidade", conteudo: matrizCard },
        {
          id: "proposta",
          rotulo: fluxo.tipo_processo === "RFI" ? "Resposta" : "Proposta",
          conteudo: <PropostaAba licitacaoId={Number(id)} versao={ws} />,
        },
      ]}
    />
  );
}
