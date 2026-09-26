import { useCallback, useEffect, useState, type FormEvent } from "react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { CamposProposta } from "@/components/sourcing/CamposProposta";
import { lerProposta } from "@/components/sourcing/lerProposta";
import { Card, SectionLabel } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import {
  API_BASE_URL,
  ApiError,
  getToken,
  mensagemErro,
  requisitar,
} from "@/lib/api";

interface Visao {
  comprador: string | null;
  processo: {
    titulo: string;
    descricao: string | null;
    tipo_processo: string;
    prazo: string | null;
    situacao: string;
  };
  requisitos: {
    id: number;
    categoria: string;
    texto: string;
    obrigatorio: boolean | null;
  }[];
  itens: {
    id: number;
    descricao: string;
    quantidade: number;
    unidade: string | null;
  }[];
  esclarecimentos: { pergunta: string; resposta: string }[];
  minhas_perguntas: { pergunta: string; resposta: string | null }[];
  participacao: {
    nome: string;
    situacao: string;
    pode_enviar: boolean;
    pode_perguntar: boolean;
  };
  minhas_propostas: {
    id: number;
    rodada: number;
    valor_total: number | null;
    anexos: string[];
  }[];
}

export type FonteConvite =
  | { tipo: "link"; token: string }
  | { tipo: "rede"; participanteId: number };

const SITUACAO: Record<string, string> = {
  ABERTO: "Aberto para respostas",
  EM_ANALISE: "Em análise pelo comprador",
  EM_NEGOCIACAO: "Em negociação",
  ENCERRADO: "Encerrado",
  CANCELADO: "Cancelado",
};

/** Resposta do fornecedor ao convite (Phase F): por link (sem login) ou pela conta da rede. Mostra só o próprio convite. */
export function PortalFornecedor({ fonte }: { fonte: FonteConvite }) {
  const [visao, setVisao] = useState<Visao | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);
  const base =
    fonte.tipo === "link"
      ? "/portal-fornecedor"
      : `/rede/convites-sourcing/${fonte.participanteId}`;
  const token = fonte.tipo === "link" ? fonte.token : null;

  const chamar = useCallback(
    <T,>(caminho: string, corpo?: unknown) =>
      requisitar<T>(`${base}${caminho}`, {
        method: corpo === undefined ? "GET" : "POST",
        body: corpo === undefined ? undefined : JSON.stringify(corpo),
        headers: token ? { "X-Convite-Token": token } : {},
      }),
    [base, token],
  );

  const carregar = useCallback(async () => {
    try {
      setVisao(await chamar<Visao>(""));
    } catch (error) {
      setErro(mensagemErro(error, "Não foi possível abrir o convite."));
    }
  }, [chamar]);

  useEffect(() => {
    carregar();
  }, [carregar]);

  async function executar(acao: () => Promise<unknown>, sucesso: string) {
    setErro(null);
    setAviso(null);
    try {
      await acao();
      setAviso(sucesso);
      await carregar();
    } catch (error) {
      setErro(mensagemErro(error, "Não foi possível concluir."));
    }
  }

  async function anexar(propostaId: number, arquivo: File) {
    const form = new FormData();
    form.append("arquivo", arquivo);
    const sessao = getToken();
    const resposta = await fetch(
      `${API_BASE_URL}${base}/propostas/${propostaId}/anexos`,
      {
        method: "POST",
        body: form,
        headers: token
          ? { "X-Convite-Token": token }
          : sessao
            ? { Authorization: `Bearer ${sessao}` }
            : {},
      },
    );
    if (!resposta.ok) {
      const corpo = await resposta.json().catch(() => ({}));
      throw new ApiError(resposta.status, corpo.detalhe ?? "Anexo recusado.");
    }
  }

  function enviar(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const arquivo = form.get("arquivo") as File | null;
    executar(async () => {
      const proposta = await chamar<{ id: number }>(
        "/propostas",
        lerProposta(form, visao?.itens ?? [], visao?.requisitos ?? []),
      );
      if (arquivo && arquivo.size > 0) await anexar(proposta.id, arquivo);
    }, "Proposta enviada ao comprador.");
  }

  if (!visao)
    return (
      <div className="p-6 text-[12px] text-muted">
        {erro ?? "Abrindo convite..."}
      </div>
    );
  const { processo, participacao } = visao;

  return (
    <div className="flex flex-col gap-3.5" data-testid="portal-fornecedor">
      <div>
        <div className="text-[11px] text-muted">
          Convite de {visao.comprador ?? "comprador"}
        </div>
        <div className="font-head text-xl font-bold">{processo.titulo}</div>
        <div className="text-[11px] text-muted">
          {processo.tipo_processo} ·{" "}
          <Badge>{SITUACAO[processo.situacao] ?? processo.situacao}</Badge> ·
          sua situação: {participacao.situacao}
          {processo.prazo &&
            ` · prazo ${new Date(processo.prazo).toLocaleString("pt-BR")}`}
        </div>
      </div>
      {erro && <div className="text-[12px] text-red">{erro}</div>}
      {aviso && <div className="text-[12px] text-green">{aviso}</div>}
      {processo.descricao && <Card>{processo.descricao}</Card>}
      <Card>
        <SectionLabel>Requisitos</SectionLabel>
        {visao.requisitos.map((r) => (
          <div key={r.id} className="text-[11px]">
            <span className="text-muted">{r.categoria}:</span> {r.texto}{" "}
            {r.obrigatorio && <Badge tone="violet">Obrigatório</Badge>}
          </div>
        ))}
        {visao.itens.map((i) => (
          <div key={i.id} className="text-[11px]">
            Item: {i.descricao} · {i.quantidade} {i.unidade ?? ""}
          </div>
        ))}
      </Card>
      <Card>
        <SectionLabel>Esclarecimentos</SectionLabel>
        {visao.esclarecimentos.map((e, i) => (
          <div key={i} className="text-[11px]">
            <b>{e.pergunta}</b> — {e.resposta}
          </div>
        ))}
        {visao.minhas_perguntas
          .filter((p) => !p.resposta)
          .map((p, i) => (
            <div key={`p-${i}`} className="text-[11px] text-muted">
              Sua pergunta aguardando resposta: {p.pergunta}
            </div>
          ))}
        {participacao.pode_perguntar && (
          <form
            className="mt-2 flex gap-2"
            onSubmit={(event) => {
              event.preventDefault();
              const alvo = event.currentTarget;
              const pergunta = String(new FormData(alvo).get("pergunta") ?? "");
              executar(async () => {
                await chamar("/perguntas", { pergunta });
                alvo.reset();
              }, "Pergunta enviada.");
            }}
          >
            <Input
              name="pergunta"
              required
              minLength={3}
              placeholder="Sua pergunta ao comprador"
              className="flex-1"
            />
            <Button type="submit" size="sm" variant="ghost">
              Perguntar
            </Button>
          </form>
        )}
      </Card>
      {participacao.pode_enviar && (
        <Card>
          <SectionLabel>Enviar proposta</SectionLabel>
          <form onSubmit={enviar} className="flex flex-wrap gap-2">
            <CamposProposta itens={visao.itens} respostas={visao.requisitos} />
            <input
              name="arquivo"
              type="file"
              accept=".pdf,.txt,application/pdf,text/plain"
              className="text-[11px]"
            />
            <Button type="submit" size="sm">
              Enviar proposta
            </Button>
          </form>
        </Card>
      )}
      <Card>
        <SectionLabel>Suas propostas</SectionLabel>
        {visao.minhas_propostas.map((p) => (
          <div key={p.id} className="text-[11px]">
            Rodada {p.rodada} ·{" "}
            {p.valor_total === null
              ? "sem valor"
              : p.valor_total.toLocaleString("pt-BR", {
                  style: "currency",
                  currency: "BRL",
                })}
            {p.anexos.length > 0 && ` · anexos: ${p.anexos.join(", ")}`}
          </div>
        ))}
        {visao.minhas_propostas.length === 0 && (
          <div className="text-[11px] text-muted">
            Nenhuma proposta enviada.
          </div>
        )}
        {![
          "DECLINOU",
          "ADJUDICADO",
          "NAO_SELECIONADO",
          "DESQUALIFICADO",
        ].includes(participacao.situacao) && (
          <Button
            className="mt-2"
            size="sm"
            variant="ghost"
            onClick={() =>
              executar(
                () => chamar("/declinar", { motivo: null }),
                "Você declinou o convite.",
              )
            }
          >
            Declinar convite
          </Button>
        )}
      </Card>
    </div>
  );
}
