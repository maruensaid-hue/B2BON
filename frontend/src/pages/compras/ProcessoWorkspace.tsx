import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";

import { ProcessWorkspace } from "@/components/sourcing/ProcessWorkspace";
import { Badge } from "@/components/ui/Badge";
import { Card, SectionLabel } from "@/components/ui/Card";
import { api, ApiError } from "@/lib/api";

interface Documento {
  id: number;
  tipo: string;
  nome_arquivo: string;
  sha256: string;
  classificacao: string;
  achados: {
    categoria: string;
    descricao: string;
    pagina: number;
    clausula: string | null;
    evidencia: string;
  }[];
}

interface Workspace {
  overview: {
    objeto: string;
    status: string;
    numero: string | null;
    valor_estimado: number | null;
  };
  documentos: Documento[];
  pesquisa_precos: {
    item: string;
    amostras: number;
    mediana: number;
    suficiente: boolean;
    fora_da_faixa: unknown[];
  }[];
  timeline: { id: number; tipo: string; descricao: string; status: string }[];
  auditoria: { evento: string; ator_id: string | null; em: string }[];
  ai_insights: {
    sinais: {
      sinais: { tipo: string; mensagem: string; severidade: string }[];
    };
    proximas_acoes: { acao: string }[];
  };
}

/** Procurement Process Workspace (Fase 10, §41). */
export function ProcessoWorkspace() {
  const { id } = useParams<{ id: string }>();
  const [ws, setWs] = useState<Workspace | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => {
    api
      .get<Workspace>(`/procurement/processos/${id}/workspace`)
      .then(setWs)
      .catch((error) =>
        setErro(
          error instanceof ApiError
            ? error.message
            : "Não foi possível carregar o processo.",
        ),
      );
  }, [id]);

  if (!ws)
    return (
      <div className="text-[12px] text-muted">{erro ?? "Carregando..."}</div>
    );

  const documentosCard = (
    <Card>
      <SectionLabel>Documentos (ETP, TR, edital...)</SectionLabel>
      <div className="flex flex-col gap-1.5 text-[11px]">
        {ws.documentos.map((d) => (
          <div key={d.id} title={`SHA-256 ${d.sha256}`}>
            <span className="text-text">{d.nome_arquivo}</span>
            <span className="text-muted">
              {" "}
              · {d.tipo} · {d.classificacao}
            </span>
            {d.achados.map((a, indice) => (
              <div key={indice} className="ml-2 text-[10px] text-muted">
                {a.categoria}: {a.descricao} (pág. {a.pagina}
                {a.clausula ? `, cl. ${a.clausula}` : ""}) —{" "}
                <i>“{a.evidencia}”</i>
              </div>
            ))}
          </div>
        ))}
        {ws.documentos.length === 0 && (
          <div className="text-muted">Nenhum documento.</div>
        )}
      </div>
    </Card>
  );
  const insightsCard = (
    <Card>
      <SectionLabel>AI Insights (sinais para revisão)</SectionLabel>
      <div className="flex flex-col gap-1.5 text-[11px]">
        {ws.ai_insights.sinais.sinais.map((s, indice) => (
          <div key={indice} className="flex items-start justify-between gap-2">
            <span className="text-text">{s.mensagem}</span>
            <Badge
              tone={
                s.severidade === "ALTA"
                  ? "red"
                  : s.severidade === "ATENCAO"
                    ? "amber"
                    : "muted"
              }
            >
              {s.severidade}
            </Badge>
          </div>
        ))}
        {ws.ai_insights.proximas_acoes.map((a, indice) => (
          <div key={indice} className="text-cyan">
            → {a.acao}
          </div>
        ))}
        {ws.ai_insights.sinais.sinais.length === 0 && (
          <div className="text-muted">Nenhum sinal.</div>
        )}
      </div>
    </Card>
  );
  const precosCard = (
    <Card>
      <SectionLabel>Pesquisa de preços</SectionLabel>
      <div className="flex flex-col gap-1 text-[11px]">
        {ws.pesquisa_precos.map((p) => (
          <div key={p.item} className="flex justify-between gap-2">
            <span className="text-text">{p.item}</span>
            <span className="text-muted">
              {p.amostras} amostra(s) · mediana{" "}
              {p.mediana.toLocaleString("pt-BR")}
              {!p.suficiente ? " · poucas amostras" : ""}
              {p.fora_da_faixa.length
                ? ` · ${p.fora_da_faixa.length} fora da faixa`
                : ""}
            </span>
          </div>
        ))}
        {ws.pesquisa_precos.length === 0 && (
          <div className="text-muted">Nenhum preço coletado.</div>
        )}
      </div>
    </Card>
  );
  const timelineCard = (
    <Card>
      <SectionLabel>Timeline e auditoria</SectionLabel>
      <div className="flex flex-col gap-1 text-[11px]">
        {ws.timeline.map((e) => (
          <div key={e.id} className="text-text">
            {e.tipo}: {e.descricao}{" "}
            <span className="text-muted">({e.status})</span>
          </div>
        ))}
        {ws.auditoria.map((a, indice) => (
          <div key={indice} className="text-[10px] text-muted">
            {new Date(a.em).toLocaleString("pt-BR")} · {a.evento} · usuário{" "}
            {a.ator_id ?? "sistema"}
          </div>
        ))}
      </div>
    </Card>
  );

  return (
    <ProcessWorkspace
      testId="processo-workspace"
      voltar={{ para: "/compras", rotulo: "Compras públicas" }}
      titulo={ws.overview.objeto}
      subtitulo={`${ws.overview.numero ?? "sem número"} · status ${ws.overview.status}`}
      abas={[
        {
          id: "visao",
          rotulo: "Visão geral",
          conteudo: insightsCard,
          contador: ws.ai_insights.sinais.sinais.length,
        },
        { id: "documentos", rotulo: "Documentos", conteudo: documentosCard },
        { id: "precos", rotulo: "Pesquisa de preços", conteudo: precosCard },
        { id: "timeline", rotulo: "Timeline", conteudo: timelineCard },
      ]}
    />
  );
}
