import { useCallback, useEffect, useState, type FormEvent, type ReactNode } from "react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { SectionLabel } from "@/components/ui/Card";
import { Input, Select } from "@/components/ui/Input";
import { api, ApiError } from "@/lib/api";

interface Evidencia {
  tipo: string;
  referencia: string | number | null;
  trecho: string;
  fonte: string;
}

interface Recomendacao {
  tipo: string;
  titulo: string;
  motivo: string;
  evidencias: Evidencia[];
  confianca: "ALTA" | "MEDIA" | "BAIXA";
  fonte: string;
  gerado_em: string;
  dados: Record<string, unknown>;
}

interface Necessidade {
  id: number;
  categoria: string;
  descricao: string;
  citacao: string | null;
  origem: "ia" | "manual";
  status: "sugerida" | "confirmada" | "descartada";
}

interface OfertaRef {
  oferta_id: number;
  nome: string;
}

interface CardOportunidade {
  metodologia: string;
  next_best_action: { status: string; recomendacoes: Recomendacao[] };
  next_best_offer: { status: string; faltando: string[]; recomendacoes: Recomendacao[]; nao_cruzados: string[] };
  discovery_gaps: {
    status: string;
    faltando: string[];
    dimensoes: Record<string, { rotulo: string; status: "CONFIRMADO" | "SUGERIDO" | "FALTANDO" }>;
    perguntas_sugeridas: string[];
  };
  meeting_intelligence: { necessidades: Necessidade[] };
  white_space: {
    produtos_atuais: OfertaRef[];
    produtos_potenciais: (OfertaRef & { fit_score: number })[];
    necessidades_nao_atendidas: { necessidade_id: number; descricao: string }[];
    potencial_estimado: number | null;
    potencial_estimado_motivo_nulo: string | null;
    sinais: Recomendacao[];
  };
  cross_sell: OfertaRef[];
  upsell: OfertaRef[];
  buying_signals: Recomendacao[];
  riscos: Recomendacao[];
  stakeholders_faltantes: Recomendacao[];
}

const CATEGORIAS: Record<string, string> = {
  dor: "Dor",
  requisito: "Requisito",
  orcamento: "Orçamento",
  autoridade: "Autoridade",
  prazo: "Prazo",
  concorrencia: "Concorrência",
  objecao: "Objeção",
  outro: "Outro",
};

const TOM_CONFIANCA = { ALTA: "green", MEDIA: "amber", BAIXA: "muted" } as const;
const TOM_DIMENSAO = { CONFIRMADO: "green", SUGERIDO: "amber", FALTANDO: "red" } as const;
const ROTULO_FONTE: Record<string, string> = {
  confirmado_por_humano: "confirmado",
  sugestao_ia_nao_confirmada: "sugestão da IA",
  cadastro: "cadastro",
  calculo_deterministico: "cálculo",
  ausencia_de_dado: "dado ausente",
};

function ItemRecomendacao({ item, extra }: { item: Recomendacao; extra?: ReactNode }) {
  return (
    <div className="rounded-md border border-border p-2 text-[11px]">
      <div className="flex items-center justify-between gap-2">
        <span className="font-semibold text-text">{item.titulo}</span>
        <Badge tone={TOM_CONFIANCA[item.confianca]}>{item.confianca}</Badge>
      </div>
      <div className="mt-0.5 text-muted">{item.motivo}</div>
      {extra}
      <details className="mt-1">
        <summary className="cursor-pointer text-[10px] text-cyan">Por quê? ({item.evidencias.length} evidência(s))</summary>
        <ul className="mt-1 flex flex-col gap-0.5 text-[10px] text-muted">
          {item.evidencias.map((evidencia, indice) => (
            <li key={indice}>
              <span className="text-text">{evidencia.trecho}</span> · {ROTULO_FONTE[evidencia.fonte] ?? evidencia.fonte}
            </li>
          ))}
        </ul>
      </details>
    </div>
  );
}

function ListaRecomendacoes({ titulo, itens, vazio }: { titulo: string; itens: Recomendacao[]; vazio: string }) {
  return (
    <div>
      <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">{titulo}</div>
      {itens.length === 0 ? (
        <div className="text-[11px] text-muted">{vazio}</div>
      ) : (
        <div className="flex flex-col gap-1.5">
          {itens.map((item, indice) => (
            <ItemRecomendacao key={indice} item={item} />
          ))}
        </div>
      )}
    </div>
  );
}

/** Opportunity Intelligence Card (Fase 6). O card é determinístico e não
 * consome crédito de IA; só "Extrair da reunião" chama a IA, e o que ela
 * sugere fica pendente até o vendedor confirmar. */
export function InteligenciaOportunidade({ negocioId }: { negocioId: number }) {
  const [card, setCard] = useState<CardOportunidade | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [extraindo, setExtraindo] = useState(false);
  const [aviso, setAviso] = useState<string | null>(null);

  const carregar = useCallback(async () => {
    try {
      setCard(await api.get<CardOportunidade>(`/inteligencia/oportunidades/${negocioId}/card`));
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível carregar a inteligência do negócio.");
    }
  }, [negocioId]);

  useEffect(() => {
    carregar();
  }, [carregar]);

  async function extrair() {
    setExtraindo(true);
    setErro(null);
    setAviso(null);
    try {
      const resultado = await api.post<{ sugeridas: Necessidade[]; descartadas_sem_evidencia: number }>(
        `/inteligencia/oportunidades/${negocioId}/necessidades/extrair`,
        {},
      );
      setAviso(
        `${resultado.sugeridas.length} necessidade(s) sugerida(s) para revisão` +
          (resultado.descartadas_sem_evidencia
            ? `; ${resultado.descartadas_sem_evidencia} descartada(s) por não terem trecho literal na reunião.`
            : "."),
      );
      await carregar();
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível extrair necessidades.");
    } finally {
      setExtraindo(false);
    }
  }

  async function revisar(id: number, status: "confirmada" | "descartada") {
    await api.patch(`/inteligencia/oportunidades/necessidades/${id}`, { status });
    await carregar();
  }

  async function registrar(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formulario = event.currentTarget;
    const form = new FormData(formulario);
    try {
      await api.post(`/inteligencia/oportunidades/${negocioId}/necessidades`, {
        categoria: String(form.get("categoria")),
        descricao: String(form.get("descricao")),
      });
      formulario.reset();
      await carregar();
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível registrar a necessidade.");
    }
  }

  if (!card) {
    return (
      <div>
        <SectionLabel>Inteligência da oportunidade</SectionLabel>
        <div className="text-[11px] text-muted">{erro ?? "Carregando..."}</div>
      </div>
    );
  }

  const nbo = card.next_best_offer;
  const discovery = card.discovery_gaps;

  return (
    <div className="flex flex-col gap-4" data-testid="inteligencia-oportunidade">
      <div className="flex items-center justify-between">
        <SectionLabel>Inteligência da oportunidade</SectionLabel>
        <span className="text-[10px] text-muted">Regras explicáveis · sem custo de IA</span>
      </div>
      {erro && <div className="text-[11px] text-red">{erro}</div>}
      {aviso && <div className="text-[11px] text-green">{aviso}</div>}

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <ListaRecomendacoes
          titulo="Próxima melhor ação"
          itens={card.next_best_action.recomendacoes}
          vazio={card.next_best_action.status === "NEGOCIO_ENCERRADO" ? "Negócio encerrado." : "Nenhuma ação pendente."}
        />

        <div>
          <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">Próxima melhor oferta</div>
          {nbo.recomendacoes.length === 0 ? (
            <div className="rounded-md border border-border p-2 text-[11px]">
              <Badge tone="amber">Informação insuficiente</Badge>
              <ul className="mt-1 list-disc pl-4 text-muted">
                {nbo.faltando.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </div>
          ) : (
            <div className="flex flex-col gap-1.5">
              {nbo.recomendacoes.map((item) => (
                <ItemRecomendacao
                  key={item.titulo}
                  item={item}
                  extra={
                    <div className="mt-1 flex flex-col gap-0.5 text-[10px] text-muted">
                      <span>Aderência: {String(item.dados.fit_score)}/100</span>
                      {(item.dados.riscos as string[]).map((risco) => (
                        <span key={risco} className="text-amber">
                          ⚠ {risco}
                        </span>
                      ))}
                    </div>
                  }
                />
              ))}
              <div className="text-[10px] text-muted">Ainda não considerado: {nbo.nao_cruzados.join("; ")}.</div>
            </div>
          )}
        </div>

        <div>
          <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">Lacunas de descoberta</div>
          <div className="flex flex-wrap gap-1.5">
            {Object.entries(discovery.dimensoes).map(([chave, dimensao]) => (
              <span key={chave} title={dimensao.status}>
                <Badge tone={TOM_DIMENSAO[dimensao.status]}>{dimensao.rotulo}</Badge>
              </span>
            ))}
          </div>
          {discovery.perguntas_sugeridas.length > 0 && (
            <ul className="mt-2 list-disc pl-4 text-[11px] text-muted">
              {discovery.perguntas_sugeridas.map((pergunta) => (
                <li key={pergunta}>{pergunta}</li>
              ))}
            </ul>
          )}
        </div>

        <div>
          <div className="mb-1.5 flex items-center justify-between">
            <span className="text-[10px] tracking-wide text-muted uppercase">Necessidades do cliente</span>
            <button type="button" onClick={extrair} disabled={extraindo} className="text-[11px] text-cyan">
              {extraindo ? "Extraindo..." : "🧠 Extrair da última reunião"}
            </button>
          </div>
          {card.meeting_intelligence.necessidades.length === 0 ? (
            <div className="text-[11px] text-muted">Nenhuma necessidade registrada.</div>
          ) : (
            <div className="flex flex-col gap-1.5">
              {card.meeting_intelligence.necessidades.map((necessidade) => (
                <div key={necessidade.id} className="rounded-md border border-border p-2 text-[11px]">
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-text">
                      <span className="text-muted">{CATEGORIAS[necessidade.categoria] ?? necessidade.categoria}:</span>{" "}
                      {necessidade.descricao}
                    </span>
                    {necessidade.status === "sugerida" ? (
                      <span className="flex shrink-0 gap-2">
                        <button type="button" className="text-green" onClick={() => revisar(necessidade.id, "confirmada")}>
                          Confirmar
                        </button>
                        <button type="button" className="text-red" onClick={() => revisar(necessidade.id, "descartada")}>
                          Descartar
                        </button>
                      </span>
                    ) : (
                      <Badge tone="green">Confirmada</Badge>
                    )}
                  </div>
                  {necessidade.citacao && <div className="mt-0.5 text-[10px] text-muted italic">“{necessidade.citacao}”</div>}
                </div>
              ))}
            </div>
          )}
          <form onSubmit={registrar} className="mt-2 flex gap-1.5">
            <Select name="categoria" defaultValue="dor" className="w-32">
              {Object.entries(CATEGORIAS).map(([valor, rotulo]) => (
                <option key={valor} value={valor}>
                  {rotulo}
                </option>
              ))}
            </Select>
            <Input name="descricao" required minLength={3} placeholder="Necessidade dita pelo cliente" />
            <Button type="submit">Adicionar</Button>
          </form>
        </div>

        <ListaRecomendacoes titulo="Riscos" itens={card.riscos} vazio="Nenhum risco identificado." />
        <ListaRecomendacoes titulo="Sinais de compra" itens={card.buying_signals} vazio="Nenhum sinal de compra registrado." />
        <ListaRecomendacoes
          titulo="Stakeholders faltando"
          itens={card.stakeholders_faltantes}
          vazio="Comitê de compra completo."
        />

        <div>
          <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">Espaço em branco na conta</div>
          <div className="flex flex-col gap-1 text-[11px] text-muted">
            <span>
              Já compra: {card.white_space.produtos_atuais.map((o) => o.nome).join(", ") || "nada ainda"}
            </span>
            <span>
              Potencial: {card.white_space.produtos_potenciais.map((o) => `${o.nome} (${o.fit_score})`).join(", ") || "—"}
            </span>
            {card.cross_sell.length > 0 && <span>Cross-sell: {card.cross_sell.map((o) => o.nome).join(", ")}</span>}
            {card.upsell.length > 0 && <span>Upsell: {card.upsell.map((o) => o.nome).join(", ")}</span>}
            <span>
              Valor potencial:{" "}
              {card.white_space.potencial_estimado !== null
                ? `R$ ${card.white_space.potencial_estimado.toLocaleString("pt-BR")}`
                : `não estimado (${card.white_space.potencial_estimado_motivo_nulo})`}
            </span>
            {card.white_space.necessidades_nao_atendidas.length > 0 && (
              <span>
                Necessidades sem oferta:{" "}
                {card.white_space.necessidades_nao_atendidas.map((n) => n.descricao).join("; ")}
              </span>
            )}
          </div>
          {card.white_space.sinais.map((sinal, indice) => (
            <div key={indice} className="mt-1.5">
              <ItemRecomendacao item={sinal} />
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
