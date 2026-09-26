import { useState, type FormEvent } from "react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, SectionLabel } from "@/components/ui/Card";
import { confirmarConsumo } from "@/lib/aiCredits";
import { api, ApiError, postFile } from "@/lib/api";

export interface Alerta {
  tipo: string;
  severidade: "alto" | "atencao" | "info";
  mensagem: string;
  evidencia: { participante_id?: number } & Record<string, unknown>;
}
export interface Inteligencia {
  alertas: Alerta[];
  proxima_acao: { acao: string; motivo: string } | null;
  aviso: string;
}
export interface DocumentoSourcing {
  id: number;
  nome_arquivo: string;
  paginas: number;
  classificacao: string;
  status_extracao: string;
}
export interface RequisitoSugerido {
  id: number;
  categoria: string;
  texto: string;
  obrigatorio: boolean | null;
  pagina: number | null;
  clausula: string | null;
  trecho: string | null;
}
export interface Sugestao {
  proposta_id: number;
  requisito_id: number;
  status: string;
  citacao: string;
  justificativa: string | null;
}

type Executar = (acao: () => Promise<unknown>) => Promise<void>;

const TOM: Record<Alerta["severidade"], "red" | "amber" | "cyan"> = {
  alto: "red",
  atencao: "amber",
  info: "cyan",
};

/** Próxima ação e alertas determinísticos (Phase G, C0): cada alerta vem do dado que o gerou. */
export function PainelInteligencia({
  inteligencia,
  nomeParticipante,
}: {
  inteligencia: Inteligencia;
  nomeParticipante: (id: number) => string;
}) {
  return (
    <Card>
      <SectionLabel>Próxima ação e alertas</SectionLabel>
      {inteligencia.proxima_acao ? (
        <div className="text-[12px]" data-testid="proxima-acao">
          <b>{inteligencia.proxima_acao.motivo}</b>
        </div>
      ) : (
        <div className="text-[11px] text-muted">Processo encerrado.</div>
      )}
      <div className="mt-2 flex flex-col gap-1 text-[11px]">
        {inteligencia.alertas.map((a, i) => (
          <div key={`${a.tipo}-${i}`}>
            <Badge tone={TOM[a.severidade]}>{a.tipo}</Badge> {a.mensagem}
            {a.evidencia.participante_id !== undefined &&
              ` (${nomeParticipante(a.evidencia.participante_id)})`}
          </div>
        ))}
      </div>
      <div className="mt-2 text-[10px] text-muted">{inteligencia.aviso}</div>
    </Card>
  );
}

/** Requirement AI (Phase G): especificação → requisitos sugeridos com trecho e página; valem só depois da revisão. */
export function EspecificacaoIA({
  url,
  documentos,
  sugeridos,
  editavel,
  ocupado,
  executar,
}: {
  url: string;
  documentos: DocumentoSourcing[];
  sugeridos: RequisitoSugerido[];
  editavel: boolean;
  ocupado: boolean;
  executar: Executar;
}) {
  const [resultado, setResultado] = useState<string | null>(null);

  function enviar(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formulario = event.currentTarget;
    const arquivo = new FormData(formulario).get("arquivo") as File | null;
    if (!arquivo || arquivo.size === 0) return;
    executar(async () => {
      await postFile(`${url}/documentos`, arquivo);
      formulario.reset();
    });
  }

  function analisar(documentoId: number) {
    setResultado(null);
    executar(async () => {
      const confirmar = await confirmarConsumo(
        `/sourcing/documentos/${documentoId}/estimativa`,
      );
      if (confirmar === null) throw new ApiError(0, "Análise cancelada.");
      const r = await api.post<{
        sugeridos: number;
        descartados_sem_evidencia: number;
        analise_parcial: boolean;
      }>(`/sourcing/documentos/${documentoId}/analisar?confirmar=${confirmar}`);
      setResultado(
        `${r.sugeridos} requisito(s) sugerido(s); ${r.descartados_sem_evidencia} descartado(s) por não estarem no texto${r.analise_parcial ? "; análise parcial (documento longo)" : ""}.`,
      );
    });
  }

  const revisar = (requisitoId: number, confirmar: boolean) =>
    executar(() =>
      api.put(`/sourcing/requisitos/${requisitoId}/revisao`, { confirmar }),
    );

  return (
    <Card>
      <SectionLabel>Especificação e requisitos sugeridos pela IA</SectionLabel>
      <div className="flex flex-col gap-1 text-[11px]">
        {documentos.map((d) => (
          <div key={d.id} className="flex items-center justify-between gap-2">
            <span>
              {d.nome_arquivo}
              <span className="text-muted">
                {" "}
                · {d.paginas} pág. · {d.classificacao} · {d.status_extracao}
              </span>
            </span>
            {editavel &&
              d.status_extracao === "PENDENTE" &&
              d.classificacao !== "RESTRICTED" && (
                <button
                  type="button"
                  className="text-cyan"
                  disabled={ocupado}
                  onClick={() => analisar(d.id)}
                >
                  🧠 Sugerir requisitos
                </button>
              )}
          </div>
        ))}
        {resultado && <div className="text-green">{resultado}</div>}
      </div>
      {editavel && (
        <form onSubmit={enviar} className="mt-2 flex items-center gap-2">
          <input
            name="arquivo"
            type="file"
            accept=".pdf,.txt,application/pdf,text/plain"
            className="text-[11px]"
          />
          <Button type="submit" size="sm" variant="ghost" disabled={ocupado}>
            Enviar especificação
          </Button>
        </form>
      )}
      <div className="mt-2 flex flex-col gap-2 text-[11px]">
        {sugeridos.map((r) => (
          <div
            key={r.id}
            className="rounded-md border border-border p-2"
            data-testid="requisito-sugerido"
          >
            <div>
              <Badge tone="amber">sugerido</Badge>{" "}
              <span className="text-muted">{r.categoria}:</span> {r.texto}{" "}
              {r.obrigatorio && <Badge tone="violet">Obrigatório</Badge>}
            </div>
            <div className="mt-1 text-muted">
              “{r.trecho}” — pág. {r.pagina}
              {r.clausula && `, item ${r.clausula}`}
            </div>
            {editavel && (
              <div className="mt-1 flex gap-2">
                <Button
                  size="sm"
                  variant="ghost"
                  disabled={ocupado}
                  onClick={() => revisar(r.id, true)}
                >
                  Confirmar
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  disabled={ocupado}
                  onClick={() => revisar(r.id, false)}
                >
                  Descartar
                </Button>
              </div>
            )}
          </div>
        ))}
      </div>
    </Card>
  );
}

/** Evaluation AI (Phase G): sugestões ancoradas no texto de cada proposta; nada vira avaliação sem o avaliador. */
export function SugerirAvaliacao({
  url,
  ocupado,
  executar,
  aoReceber,
}: {
  url: string;
  ocupado: boolean;
  executar: Executar;
  aoReceber: (sugestoes: Sugestao[]) => void;
}) {
  const [resumo, setResumo] = useState<string | null>(null);
  return (
    <Card>
      <SectionLabel>Avaliação assistida</SectionLabel>
      <div className="text-[10px] text-muted">
        A IA lê cada proposta separadamente e sugere o status só quando acha o
        trecho na própria proposta. Você decide o que aplicar.
      </div>
      <Button
        className="mt-2"
        size="sm"
        variant="ghost"
        disabled={ocupado}
        onClick={() =>
          executar(async () => {
            const confirmar = await confirmarConsumo(
              `${url}/avaliacao-ia/estimativa`,
            );
            if (confirmar === null) throw new ApiError(0, "Cancelado.");
            const r = await api.post<{
              sugestoes: Sugestao[];
              descartadas_sem_evidencia: number;
              propostas_analisadas: number;
            }>(`${url}/avaliacao-ia?confirmar=${confirmar}`);
            aoReceber(r.sugestoes);
            setResumo(
              `${r.sugestoes.length} sugestão(ões) em ${r.propostas_analisadas} proposta(s); ${r.descartadas_sem_evidencia} descartada(s) sem trecho da proposta.`,
            );
          })
        }
      >
        🧠 Sugerir avaliação
      </Button>
      {resumo && <div className="mt-1 text-[11px] text-green">{resumo}</div>}
    </Card>
  );
}
