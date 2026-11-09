import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import { Select } from "@/components/ui/Input";
import { api, ApiError } from "@/lib/api";

interface ConversaResumo {
  id: number;
  conta_id: number;
  conta_nome: string;
  decisor_id: number;
  decisor_nome: string;
  decisor_cargo: string | null;
  canal: string;
  etapa_atual: string;
  status: string;
  score_total: number | null;
  total_turnos: number;
  ultima_fala: string | null;
  ultima_direcao: string | null;
  atualizado_em: string;
  descadastrado: boolean;
}

interface Turno {
  id: number;
  direcao: string;
  conteudo: string;
  criado_em: string;
}

interface ConversaComTurnos {
  conversa: { id: number; status: string; etapa_atual: string; motivo_devolucao: string | null };
  turnos: Turno[];
}

// Roteiro S.H.A.R.K.: a ordem em que a qualificação avança.
const ETAPAS: [string, string][] = [
  ["dores", "Dores"],
  ["contexto", "Contexto"],
  ["orcamento", "Orçamento"],
  ["autoridade", "Autoridade"],
  ["timing", "Momento"],
  ["concluida", "Concluída"],
];
const ROTULO_ETAPA = Object.fromEntries(ETAPAS);

const STATUS: Record<string, { rotulo: string; tom: "cyan" | "green" | "amber" | "muted" }> = {
  em_andamento: { rotulo: "Em andamento", tom: "cyan" },
  transferida_humano: { rotulo: "Com o vendedor", tom: "amber" },
  concluida: { rotulo: "Qualificada", tom: "green" },
  devolvida: { rotulo: "Devolvida à nutrição", tom: "muted" },
};

function quando(data: string): string {
  return new Date(`${data}${data.endsWith("Z") ? "" : "Z"}`).toLocaleString("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function ProgressoEtapas({ atual }: { atual: string }) {
  const indice = ETAPAS.findIndex(([chave]) => chave === atual);
  return (
    <div className="flex flex-wrap gap-1">
      {ETAPAS.slice(0, -1).map(([chave, rotulo], i) => (
        <span
          key={chave}
          className={`rounded px-1.5 py-0.5 text-[10px] ${
            indice === -1 || i < indice || atual === "concluida" ? "bg-green/15 text-green" : i === indice ? "bg-cyan/15 text-cyan" : "bg-muted/10 text-muted"
          }`}
        >
          {rotulo}
        </span>
      ))}
    </div>
  );
}

export function Conversas() {
  const [conversas, setConversas] = useState<ConversaResumo[] | null>(null);
  const [filtro, setFiltro] = useState("");
  const [selecionada, setSelecionada] = useState<number | null>(null);
  const [detalhe, setDetalhe] = useState<ConversaComTurnos | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => {
    setErro(null);
    api
      .get<ConversaResumo[]>(`/conversas${filtro ? `?status=${filtro}` : ""}`)
      .then((lista) => {
        setConversas(lista);
        setSelecionada((atual) => (atual !== null && lista.some((c) => c.id === atual) ? atual : lista[0]?.id ?? null));
      })
      .catch((e) => setErro(e instanceof ApiError ? e.message : "Não foi possível carregar as conversas."));
  }, [filtro]);

  useEffect(() => {
    if (selecionada === null) {
      setDetalhe(null);
      return;
    }
    api
      .get<ConversaComTurnos>(`/conversas/${selecionada}`)
      .then(setDetalhe)
      .catch((e) => setErro(e instanceof ApiError ? e.message : "Não foi possível abrir a conversa."));
  }, [selecionada]);

  const resumo = conversas?.find((c) => c.id === selecionada) ?? null;

  return (
    <div className="p-5.5">
      <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
        <div>
          <div className="font-head text-xl font-bold">Conversas</div>
          <div className="mt-0.5 text-[11px] text-muted">
            Quem respondeu à prospecção, em que etapa da qualificação está e o que foi dito. As respostas da plataforma são preparadas
            como rascunho e só saem depois de aprovadas em <Link to="/aprovacoes" className="text-cyan hover:underline">Aprovações</Link>.
          </div>
        </div>
        <Select value={filtro} onChange={(event) => setFiltro(event.target.value)} className="w-48">
          <option value="">Todas</option>
          {Object.entries(STATUS).map(([chave, { rotulo }]) => (
            <option key={chave} value={chave}>
              {rotulo}
            </option>
          ))}
        </Select>
      </div>

      {erro && <div className="mb-3 text-[12px] text-red">{erro}</div>}

      {conversas === null ? (
        <div className="text-[12px] text-muted">Carregando…</div>
      ) : conversas.length === 0 ? (
        <Card>
          <div className="text-[12px] text-muted">
            Nenhuma conversa ainda. Quando um contato responder a uma mensagem de cadência (WhatsApp ou e-mail), a conversa aparece aqui.
          </div>
        </Card>
      ) : (
        <div className="grid gap-4 lg:grid-cols-[minmax(0,360px)_1fr]">
          <div className="flex flex-col gap-2">
            {conversas.map((conversa) => {
              const status = STATUS[conversa.status] ?? { rotulo: conversa.status, tom: "muted" as const };
              return (
                <button
                  key={conversa.id}
                  type="button"
                  onClick={() => setSelecionada(conversa.id)}
                  className={`rounded-lg border p-3 text-left transition-colors ${
                    conversa.id === selecionada ? "border-cyan bg-cyan/5" : "border-border bg-surf hover:border-cyan/50"
                  }`}
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <div className="truncate text-[13px] font-medium text-text">{conversa.decisor_nome}</div>
                      <div className="truncate text-[11px] text-muted">
                        {conversa.decisor_cargo ? `${conversa.decisor_cargo} · ` : ""}
                        {conversa.conta_nome}
                      </div>
                    </div>
                    <span className="flex shrink-0 flex-col items-end gap-1 whitespace-nowrap">
                      <Badge tone={status.tom}>{status.rotulo}</Badge>
                      {conversa.descadastrado && <Badge tone="red">Descadastrado</Badge>}
                    </span>
                  </div>
                  {conversa.ultima_fala && (
                    <div className="mt-1.5 line-clamp-2 text-[11px] text-muted">
                      {conversa.ultima_direcao === "entrada" ? "" : "Plataforma: "}
                      {conversa.ultima_fala}
                    </div>
                  )}
                  <div className="mt-1.5 flex items-center justify-between text-[10px] text-muted">
                    <span>
                      {conversa.canal === "whatsapp" ? "WhatsApp" : "E-mail"} · {ROTULO_ETAPA[conversa.etapa_atual] ?? conversa.etapa_atual}
                    </span>
                    <span>{quando(conversa.atualizado_em)}</span>
                  </div>
                </button>
              );
            })}
          </div>

          <Card>
            {resumo && detalhe ? (
              <div className="flex flex-col gap-3">
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div>
                    <div className="text-[14px] font-medium text-text">{resumo.decisor_nome}</div>
                    <div className="text-[11px] text-muted">
                      {resumo.decisor_cargo ? `${resumo.decisor_cargo} · ` : ""}
                      {resumo.conta_nome}
                    </div>
                  </div>
                  <div className="text-right">
                    <div className="text-[10px] uppercase tracking-wide text-muted">Nota de qualificação</div>
                    <div className="font-head text-lg font-bold text-text">
                      {resumo.score_total === null ? "—" : resumo.score_total.toFixed(0)}
                    </div>
                  </div>
                </div>
                <ProgressoEtapas atual={detalhe.conversa.etapa_atual} />
                {resumo.descadastrado && (
                  <div className="rounded-lg bg-red/10 p-2 text-[11px] text-red">
                    Este contato pediu para não receber mais mensagens (descadastro). Nenhuma mensagem sai mais para ele, em nenhum canal.
                  </div>
                )}
                {detalhe.conversa.status === "transferida_humano" && (
                  <div className="rounded-lg bg-amber/10 p-2 text-[11px] text-amber">
                    A conversa saiu do roteiro e foi passada ao vendedor: responda pessoalmente.
                  </div>
                )}
                {detalhe.conversa.motivo_devolucao && (
                  <div className="rounded-lg bg-surf2 p-2 text-[11px] text-muted">Devolvida: {detalhe.conversa.motivo_devolucao}</div>
                )}
                <div className="flex flex-col gap-2">
                  {detalhe.turnos.map((turno) => (
                    <div key={turno.id} className={`flex ${turno.direcao === "entrada" ? "justify-start" : "justify-end"}`}>
                      <div
                        className={`max-w-[85%] rounded-lg px-3 py-2 text-[12px] ${
                          turno.direcao === "entrada" ? "bg-surf2 text-text" : "bg-cyan/10 text-text"
                        }`}
                      >
                        <div className="mb-0.5 text-[10px] text-muted">
                          {turno.direcao === "entrada" ? resumo.decisor_nome : "Plataforma (vai para aprovação)"} · {quando(turno.criado_em)}
                        </div>
                        <div className="whitespace-pre-wrap">{turno.conteudo}</div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ) : (
              <div className="text-[12px] text-muted">Escolha uma conversa.</div>
            )}
          </Card>
        </div>
      )}
    </div>
  );
}
