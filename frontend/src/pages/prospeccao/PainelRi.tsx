import { useCallback, useEffect, useState } from "react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Input, Select } from "@/components/ui/Input";
import { SeletorArquivo } from "@/components/ui/SeletorArquivo";
import { api, ApiError, postFile } from "@/lib/api";

interface Fonte {
  documento: string | null;
  url: string | null;
  data_publicacao: string | null;
}

interface Indicador {
  id: number;
  origem: "ri" | "site";
  documento_id?: number;
  nome: string;
  tipo: string;
  valor: number | null;
  moeda: string | null;
  valor_original: string | null;
  periodo: string | null;
  pagina: number | null;
  estado_validacao: string;
  fonte: Fonte | null;
}

interface SinalRi {
  tipo: string;
  pagina: number;
  trecho: string;
  documento: string;
}

interface Financeiro {
  indicadores: Indicador[];
  sinais: SinalRi[];
  documentos: number;
  aviso: string;
}

interface DocumentoRi {
  id: number;
  nome_arquivo: string | null;
  titulo: string | null;
  url_fonte: string | null;
  tipo_documento: string;
  estado: string;
  paginas: number | null;
  avisos: string[];
  indicadores_total: number;
  data_publicacao: string | null;
}

const TIPOS: Record<string, string> = {
  relatorio_anual: "Relatório anual",
  resultado_trimestral: "Resultado trimestral",
  demonstracoes_financeiras: "Demonstrações financeiras",
  apresentacao_resultados: "Apresentação de resultados",
  relatorio_administracao: "Relatório da administração",
  outro: "Outro",
};

const ESTADO_DOCUMENTO: Record<string, { rotulo: string; tom: "green" | "amber" | "muted" | "red" }> = {
  processado: { rotulo: "lido", tom: "green" },
  sem_dados_financeiros: { rotulo: "sem números encontrados", tom: "amber" },
  processando: { rotulo: "lendo", tom: "muted" },
};

const ESTADO_INDICADOR: Record<string, { rotulo: string; tom: "green" | "amber" | "red" }> = {
  conferido_manualmente: { rotulo: "conferido", tom: "green" },
  extraido_automaticamente: { rotulo: "não conferido", tom: "amber" },
  rejeitado: { rotulo: "rejeitado", tom: "red" },
};

const rotuloNome = (nome: string) => {
  const texto = nome.replace(/_/g, " ");
  return texto.charAt(0).toUpperCase() + texto.slice(1);
};

function valorExibido(indicador: Indicador): string {
  if (indicador.valor_original) return indicador.valor_original;
  if (indicador.valor === null) return "—";
  const numero = indicador.valor.toLocaleString("pt-BR", { maximumFractionDigits: 2 });
  return indicador.moeda ? `${indicador.moeda} ${numero}` : numero;
}

/** Relações com Investidores da conta: documentos publicados pela própria empresa (PDF ou link), os números lidos deles e do site, e
 * os fatos citados (aquisição, expansão...). Sem IA: números extraídos por regra, com a página de onde vieram; quem confere é a pessoa. */
export function PainelRi({ contaId }: { contaId: number }) {
  const [financeiro, setFinanceiro] = useState<Financeiro | null>(null);
  const [documentos, setDocumentos] = useState<DocumentoRi[]>([]);
  const [aberto, setAberto] = useState(false);
  const [url, setUrl] = useState("");
  const [tipo, setTipo] = useState("relatorio_anual");
  const [ocupado, setOcupado] = useState<string | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  const carregar = useCallback(async () => {
    const [f, d] = await Promise.all([
      api.get<Financeiro>(`/contas/${contaId}/ri/financeiro`),
      api.get<DocumentoRi[]>(`/contas/${contaId}/ri/documentos`),
    ]);
    setFinanceiro(f);
    setDocumentos(d);
  }, [contaId]);

  useEffect(() => {
    carregar().catch(() => setFinanceiro(null));
  }, [carregar]);

  async function executar(nome: string, acao: () => Promise<unknown>) {
    setErro(null);
    setOcupado(nome);
    try {
      await acao();
      await carregar();
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível concluir. Tente de novo.");
    } finally {
      setOcupado(null);
    }
  }

  const enviarLink = () =>
    executar("link", async () => {
      await api.post(`/contas/${contaId}/ri/documentos/url`, { url: url.trim(), tipo_documento: tipo });
      setUrl("");
    });

  const enviarArquivo = (arquivo: File) =>
    executar("arquivo", () => postFile(`/contas/${contaId}/ri/documentos`, arquivo, { tipo_documento: tipo }));

  const validar = (indicador: Indicador, estado: string) =>
    executar(`validar-${indicador.id}`, () =>
      api.post(`/contas/${contaId}/ri/documentos/${indicador.documento_id}/indicadores/${indicador.id}/validar`, { estado }),
    );

  const indicadores = financeiro?.indicadores ?? [];
  const resumo = indicadores.length
    ? `${indicadores.length} número(s) de ${financeiro?.documentos ?? 0} documento(s) e do site`
    : "nenhum número ainda";

  return (
    <div className="mb-4">
      <button type="button" className="mb-1.5 flex w-full items-center justify-between text-left" onClick={() => setAberto(!aberto)}>
        <span className="text-[10px] tracking-wide text-muted uppercase">Relações com Investidores (RI)</span>
        <span className="text-[11px] text-muted">
          {resumo} {aberto ? "▲" : "▼"}
        </span>
      </button>

      {aberto && (
        <div className="flex flex-col gap-3 rounded-md border border-border p-3 text-[11px]">
          <div className="text-muted">
            Envie relatórios publicados pela própria empresa (relatório anual, resultados, demonstrações). O sistema lê os números escritos
            com moeda e as menções a aquisição, expansão e investimento, sempre com a página de origem. O arquivo não é guardado.
          </div>

          <div className="flex flex-col gap-2">
            <div className="flex flex-wrap items-end gap-2">
              <div className="w-56">
                <Select value={tipo} onChange={(e) => setTipo(e.target.value)} aria-label="Tipo de documento">
                  {Object.entries(TIPOS).map(([valor, rotulo]) => (
                    <option key={valor} value={valor}>
                      {rotulo}
                    </option>
                  ))}
                </Select>
              </div>
              <SeletorArquivo accept="application/pdf,.pdf" disabled={ocupado !== null} onSelecionar={enviarArquivo} rotulo="Enviar PDF" />
            </div>
            <div className="flex gap-2">
              <Input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="ou cole o link do PDF no site de RI (https://...)" />
              <Button type="button" size="sm" disabled={ocupado !== null || url.trim().length < 8} onClick={enviarLink}>
                {ocupado === "link" ? "Lendo..." : "Ler link"}
              </Button>
            </div>
            {ocupado === "arquivo" && <div className="text-muted">Lendo o PDF...</div>}
          </div>

          {erro && <div className="text-red">{erro}</div>}

          {documentos.length > 0 && (
            <div>
              <div className="mb-1 font-semibold text-text">Documentos</div>
              <div className="flex flex-col gap-1">
                {documentos.map((documento) => {
                  const estado = ESTADO_DOCUMENTO[documento.estado] ?? { rotulo: documento.estado, tom: "muted" as const };
                  return (
                    <div key={documento.id} className="border-b border-border py-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="text-text">{documento.titulo || documento.nome_arquivo || documento.url_fonte}</span>
                        <Badge tone="muted">{TIPOS[documento.tipo_documento] ?? documento.tipo_documento}</Badge>
                        <Badge tone={estado.tom}>{estado.rotulo}</Badge>
                        <span className="text-muted">
                          {documento.indicadores_total} número(s){documento.paginas ? ` · ${documento.paginas} pág.` : ""}
                        </span>
                        <span className="ml-auto flex gap-1">
                          <Button
                            type="button"
                            size="sm"
                            disabled={ocupado !== null}
                            onClick={() => executar(`reprocessar-${documento.id}`, () => api.post(`/contas/${contaId}/ri/documentos/${documento.id}/reprocessar`))}
                          >
                            Ler de novo
                          </Button>
                          <Button
                            type="button"
                            size="sm"
                            variant="danger"
                            disabled={ocupado !== null}
                            onClick={() => {
                              if (window.confirm("Excluir este documento e os números lidos dele?")) {
                                void executar(`excluir-${documento.id}`, () => api.delete(`/contas/${contaId}/ri/documentos/${documento.id}`));
                              }
                            }}
                          >
                            Excluir
                          </Button>
                        </span>
                      </div>
                      {documento.avisos.length > 0 && <div className="mt-0.5 text-muted">{documento.avisos.join(" ")}</div>}
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {indicadores.length > 0 && (
            <div>
              <div className="mb-1 font-semibold text-text">Números</div>
              <div className="flex flex-col gap-1">
                {indicadores.map((indicador) => {
                  const estado = ESTADO_INDICADOR[indicador.estado_validacao] ?? { rotulo: indicador.estado_validacao, tom: "amber" as const };
                  const origem = indicador.origem === "site" ? "site" : `${indicador.fonte?.documento ?? "documento"}${indicador.pagina ? `, p. ${indicador.pagina}` : ""}`;
                  return (
                    <div key={`${indicador.origem}-${indicador.id}`} className="flex flex-wrap items-center gap-2 border-b border-border py-1">
                      <span className="text-text">{rotuloNome(indicador.nome)}</span>
                      <span className="font-semibold text-text">{valorExibido(indicador)}</span>
                      {indicador.periodo && <span className="text-muted">{indicador.periodo}</span>}
                      {indicador.tipo === "derivado" && <Badge tone="violet">calculado</Badge>}
                      <Badge tone={estado.tom}>{estado.rotulo}</Badge>
                      <span className="text-muted">fonte: {origem}</span>
                      {indicador.origem === "ri" && indicador.estado_validacao !== "conferido_manualmente" && (
                        <span className="ml-auto flex gap-1">
                          <Button type="button" size="sm" disabled={ocupado !== null} onClick={() => validar(indicador, "conferido_manualmente")}>
                            Conferido
                          </Button>
                          <Button type="button" size="sm" variant="danger" disabled={ocupado !== null} onClick={() => validar(indicador, "rejeitado")}>
                            Rejeitar
                          </Button>
                        </span>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {(financeiro?.sinais.length ?? 0) > 0 && (
            <div>
              <div className="mb-1 font-semibold text-text">Fatos citados</div>
              <div className="flex flex-col gap-1">
                {financeiro?.sinais.map((sinal, indice) => (
                  <div key={indice} className="border-b border-border py-1">
                    <Badge tone="cyan">{rotuloNome(sinal.tipo)}</Badge>{" "}
                    <span className="text-text">“{sinal.trecho}”</span>{" "}
                    <span className="text-muted">
                      ({sinal.documento}, p. {sinal.pagina})
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {financeiro && <div className="text-muted">{financeiro.aviso}</div>}
        </div>
      )}
    </div>
  );
}
