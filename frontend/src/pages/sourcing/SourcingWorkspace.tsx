import { useCallback, useEffect, useState, type FormEvent } from "react";
import { useParams } from "react-router-dom";

import { ProcessWorkspace } from "@/components/sourcing/ProcessWorkspace";
import { CamposProposta } from "@/components/sourcing/CamposProposta";
import { lerProposta } from "@/components/sourcing/lerProposta";
import { ProximosStatus } from "@/components/sourcing/ProximosStatus";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, SectionLabel } from "@/components/ui/Card";
import { Input, Select } from "@/components/ui/Input";
import { api, getBlob, mensagemErro } from "@/lib/api";
import {
  EspecificacaoIA,
  PainelInteligencia,
  SugerirAvaliacao,
  type DocumentoSourcing,
  type Inteligencia,
  type Sugestao,
} from "@/pages/sourcing/InteligenciaSourcing";
import {
  CATEGORIAS_SOURCING,
  ROTULO_PARTICIPANTE,
  ROTULO_STATUS_SOURCING,
  TIPOS_SOURCING,
  type ProcessoSourcing,
} from "@/pages/sourcing/tipos";

interface Requisito {
  id: number;
  categoria: string;
  texto: string;
  obrigatorio: boolean | null;
  peso: number | null;
  fonte: string;
  status_revisao: string;
  pagina: number | null;
  clausula: string | null;
  trecho: string | null;
}
interface Item {
  id: number;
  descricao: string;
  quantidade: number;
  unidade: string | null;
}
interface Participante {
  id: number;
  nome: string;
  origem_descoberta: string;
  status: string;
  motivo: string | null;
  historico: {
    processos: number;
    respondeu: number;
    declinou: number;
    adjudicado: number;
    desqualificado: number;
  } | null;
}
interface Avaliacao {
  requisito_id: number;
  resposta: string | null;
  status: string | null;
  nota: number | null;
}
interface Proposta {
  id: number;
  participante_id: number;
  rodada: number;
  tipo: string;
  valor_total: number | null;
  prazo_entrega_dias: number | null;
  condicoes_pagamento: string | null;
  canal: string;
  avaliacoes: Avaliacao[];
}
interface Workspace {
  processo: ProcessoSourcing;
  fluxo: {
    codigo: string;
    ruleset: { codigo: string; fonte: string } | null;
    proximos_status: string[];
    aceita_aprovacao: boolean;
    aceita_contrato: boolean;
    final: boolean;
    recebe_propostas: boolean;
    com_itens: boolean;
  };
  aprovacao: {
    participante_id: number;
    justificativa: string;
    situacao: string;
    motivo: string | null;
  } | null;
  requisitos: Requisito[];
  itens: Item[];
  participantes: Participante[];
  propostas: Proposta[];
  contratos: {
    id: number;
    contraparte_nome: string;
    numero: string | null;
    valor_inicial: number | null;
    status: string;
  }[];
  esclarecimentos: {
    id: number;
    participante_id: number;
    pergunta: string;
    resposta: string | null;
  }[];
  anexos: { id: number; proposta_id: number; nome_arquivo: string }[];
  documentos: DocumentoSourcing[];
  inteligencia: Inteligencia;
}
interface Candidato {
  origem: string;
  fornecedor_id?: number;
  empresa_rede_tenant_id?: string;
  nome: string;
  pontuacao: number;
  motivos: string[];
  faltantes: string[];
}
interface LinhaComparacao {
  participante_id: number;
  participante: string;
  situacao: string;
  rodada: number;
  tecnico: {
    obrigatorios: number;
    obrigatorios_atendidos: number;
    nota_ponderada: number | null;
    requisitos_sem_avaliacao: number[];
  };
  comercial: {
    valor_total: number | null;
    prazo_entrega_dias: number | null;
    condicoes_pagamento: string | null;
  };
  risco: string | null;
}
interface Comparacao {
  linhas: LinhaComparacao[];
  destaques: { menor_valor: number | null; maior_nota: number | null };
  aviso: string;
}

const STATUS_AVALIACAO = [
  "COMPLIANT",
  "PARTIALLY_COMPLIANT",
  "NON_COMPLIANT",
  "UNKNOWN",
  "REQUIRES_REVIEW",
];
const dinheiro = (v: number | null) =>
  v === null
    ? "—"
    : v.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });

/** Workspace do Strategic Sourcing (Phase E) sobre o ProcessWorkspace compartilhado. */
export function SourcingWorkspace() {
  const { id } = useParams<{ id: string }>();
  const [ws, setWs] = useState<Workspace | null>(null);
  const [candidatos, setCandidatos] = useState<Candidato[] | null>(null);
  const [comparacao, setComparacao] = useState<Comparacao | null>(null);
  const [link, setLink] = useState<{
    participanteId: number;
    url: string;
  } | null>(null);
  const [sugestoes, setSugestoes] = useState<Sugestao[]>([]);
  const [erro, setErro] = useState<string | null>(null);
  const [ocupado, setOcupado] = useState(false);
  const url = `/sourcing/processos/${id}`;

  const carregar = useCallback(async () => {
    try {
      setWs(await api.get<Workspace>(`${url}/workspace`));
      setComparacao(await api.get<Comparacao>(`${url}/comparacao`));
    } catch (error) {
      setErro(mensagemErro(error, "Não foi possível carregar o processo."));
    }
  }, [url]);

  useEffect(() => {
    carregar();
  }, [carregar]);

  async function executar(acao: () => Promise<unknown>) {
    setErro(null);
    setOcupado(true);
    try {
      await acao();
      await carregar();
    } catch (error) {
      setErro(mensagemErro(error, "Não foi possível concluir a ação."));
    } finally {
      setOcupado(false);
    }
  }

  function formulario(acao: (form: FormData) => Promise<unknown>) {
    return (event: FormEvent<HTMLFormElement>) => {
      event.preventDefault();
      const alvo = event.currentTarget;
      const form = new FormData(alvo);
      executar(async () => {
        await acao(form);
        alvo.reset();
      });
    };
  }

  if (!ws)
    return (
      <div className="text-[12px] text-muted">{erro ?? "Carregando..."}</div>
    );
  const { processo, fluxo } = ws;
  const editavel = ["RASCUNHO", "PUBLICADO"].includes(processo.status);
  const vigentes = ws.requisitos.filter(
    (r) => r.status_revisao === "confirmado",
  );
  const nomeParticipante = (pid: number) =>
    ws.participantes.find((p) => p.id === pid)?.nome ?? `#${pid}`;
  const texto = (form: FormData, campo: string) =>
    String(form.get(campo) ?? "").trim() || null;
  const numero = (form: FormData, campo: string) =>
    texto(form, campo) === null ? null : Number(form.get(campo));

  const andamento = (
    <Card>
      <SectionLabel>Andamento</SectionLabel>
      <div className="text-[11px] text-muted">
        Status{" "}
        <b className="text-text">
          {ROTULO_STATUS_SOURCING[processo.status] ?? processo.status}
        </b>{" "}
        · fluxo {fluxo.codigo}
        {fluxo.ruleset && ` · ${fluxo.ruleset.fonte}`}
      </div>
      <ProximosStatus
        proximos={fluxo.proximos_status}
        rotulos={ROTULO_STATUS_SOURCING}
        ocupado={ocupado}
        aoEscolher={(status) =>
          executar(() => api.post(`${url}/status`, { status }))
        }
      />
      {fluxo.aceita_aprovacao && (
        <form
          className="mt-3 flex flex-wrap gap-2"
          onSubmit={formulario((form) =>
            api.post(`${url}/aprovacao`, {
              participante_id: Number(form.get("participante_id")),
              justificativa: String(form.get("justificativa") ?? ""),
            }),
          )}
        >
          <Select name="participante_id" className="w-44">
            {ws.participantes
              .filter((p) => !["DESQUALIFICADO", "DECLINOU"].includes(p.status))
              .map((p) => (
                <option key={p.id} value={p.id}>
                  {p.nome}
                </option>
              ))}
          </Select>
          <Input
            name="justificativa"
            required
            placeholder="Justificativa da escolha"
            className="flex-1"
          />
          <Button type="submit" size="sm" disabled={ocupado}>
            Solicitar aprovação
          </Button>
        </form>
      )}
      {ws.aprovacao && (
        <div className="mt-3 text-[11px]">
          Aprovação:{" "}
          <Badge
            tone={
              ws.aprovacao.situacao === "APROVADA"
                ? "green"
                : ws.aprovacao.situacao === "RECUSADA"
                  ? "red"
                  : "amber"
            }
          >
            {ws.aprovacao.situacao}
          </Badge>{" "}
          {nomeParticipante(ws.aprovacao.participante_id)} —{" "}
          {ws.aprovacao.justificativa}
          {ws.aprovacao.motivo ? ` (motivo: ${ws.aprovacao.motivo})` : ""}
          {ws.aprovacao.situacao === "PENDENTE" && (
            <form
              className="mt-2 flex flex-wrap gap-2"
              onSubmit={formulario((form) =>
                api.put(`${url}/aprovacao`, {
                  aprovar: form.get("decisao") === "aprovar",
                  motivo: texto(form, "motivo"),
                }),
              )}
            >
              <Select name="decisao" className="w-32">
                <option value="aprovar">Aprovar</option>
                <option value="recusar">Recusar</option>
              </Select>
              <Input
                name="motivo"
                placeholder="Motivo (obrigatório para recusar)"
                className="flex-1"
              />
              <Button type="submit" size="sm" disabled={ocupado}>
                Decidir (administrador)
              </Button>
            </form>
          )}
        </div>
      )}
      {fluxo.aceita_contrato && (
        <form
          className="mt-3 flex flex-wrap gap-2"
          onSubmit={formulario((form) =>
            api.post(`${url}/contrato`, {
              numero: texto(form, "numero"),
              vigencia_inicio: texto(form, "inicio"),
              vigencia_fim: texto(form, "fim"),
            }),
          )}
        >
          <Input
            name="numero"
            placeholder="Número do contrato"
            className="w-40"
          />
          <Input name="inicio" type="date" className="w-36" />
          <Input name="fim" type="date" className="w-36" />
          <Button type="submit" size="sm" disabled={ocupado}>
            Registrar contrato
          </Button>
        </form>
      )}
      {ws.contratos.map((c) => (
        <div key={c.id} className="mt-2 text-[11px] text-muted">
          Contrato {c.numero ?? c.id} com {c.contraparte_nome} ·{" "}
          {dinheiro(c.valor_inicial)} · {c.status}
        </div>
      ))}
    </Card>
  );

  const requisitos = (
    <div className="grid grid-cols-1 gap-3.5 lg:grid-cols-2">
      <Card>
        <SectionLabel>Requisitos e critérios</SectionLabel>
        <div className="flex flex-col gap-1 text-[11px]">
          {vigentes.map((r) => (
            <div key={r.id} className="border-b border-border py-1">
              <span className="text-muted">{r.categoria}:</span> {r.texto}{" "}
              {r.obrigatorio && <Badge tone="violet">Obrigatório</Badge>}{" "}
              {r.peso !== null && <Badge>peso {r.peso}</Badge>}
            </div>
          ))}
          {vigentes.length === 0 && (
            <div className="text-muted">Nenhum requisito.</div>
          )}
        </div>
        {editavel && (
          <form
            className="mt-2 flex flex-wrap gap-2"
            onSubmit={formulario((form) =>
              api.post(`${url}/requisitos`, {
                categoria: String(form.get("categoria")),
                texto: String(form.get("texto")),
                obrigatorio: form.get("obrigatorio") === "on" ? true : null,
                peso: numero(form, "peso"),
              }),
            )}
          >
            <Select name="categoria" className="w-44">
              {CATEGORIAS_SOURCING.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </Select>
            <Input
              name="texto"
              required
              minLength={3}
              placeholder="Requisito ou pergunta"
              className="flex-1"
            />
            <Input
              name="peso"
              type="number"
              min={0.1}
              step="0.1"
              placeholder="Peso"
              className="w-20"
            />
            <label className="flex items-center gap-1 text-[11px]">
              <input type="checkbox" name="obrigatorio" /> obrigatório
            </label>
            <Button type="submit" size="sm" disabled={ocupado}>
              Adicionar
            </Button>
          </form>
        )}
      </Card>
      <EspecificacaoIA
        url={url}
        documentos={ws.documentos}
        sugeridos={ws.requisitos.filter((r) => r.status_revisao === "sugerido")}
        editavel={editavel}
        ocupado={ocupado}
        executar={executar}
      />
      {fluxo.com_itens && (
        <Card>
          <SectionLabel>Itens da cotação</SectionLabel>
          <div className="flex flex-col gap-1 text-[11px]">
            {ws.itens.map((i) => (
              <div key={i.id}>
                {i.descricao} · {i.quantidade} {i.unidade ?? ""}
              </div>
            ))}
            {ws.itens.length === 0 && (
              <div className="text-muted">Nenhum item.</div>
            )}
          </div>
          {editavel && (
            <form
              className="mt-2 flex flex-wrap gap-2"
              onSubmit={formulario((form) =>
                api.post(`${url}/itens`, {
                  descricao: String(form.get("descricao")),
                  quantidade: Number(form.get("quantidade")),
                  unidade: texto(form, "unidade"),
                }),
              )}
            >
              <Input
                name="descricao"
                required
                placeholder="Item"
                className="flex-1"
              />
              <Input
                name="quantidade"
                type="number"
                min={0.0001}
                step="any"
                required
                placeholder="Qtd."
                className="w-20"
              />
              <Input name="unidade" placeholder="Un." className="w-16" />
              <Button type="submit" size="sm" disabled={ocupado}>
                Adicionar
              </Button>
            </form>
          )}
        </Card>
      )}
    </div>
  );

  const fornecedores = (
    <div className="grid grid-cols-1 gap-3.5 lg:grid-cols-2">
      <Card>
        <SectionLabel>Descoberta de fornecedores</SectionLabel>
        <div className="text-[10px] text-muted">
          Seu cadastro e perfis públicos da Business Network; nada do processo é
          exposto.
        </div>
        <Button
          className="mt-2"
          size="sm"
          variant="ghost"
          disabled={ocupado}
          onClick={() =>
            executar(async () =>
              setCandidatos(
                (
                  await api.post<{ candidatos: Candidato[] }>(
                    `${url}/descoberta`,
                    {},
                  )
                ).candidatos,
              ),
            )
          }
        >
          Buscar candidatos
        </Button>
        <div className="mt-2 flex flex-col gap-1 text-[11px]">
          {(candidatos ?? []).map((c) => (
            <div
              key={`${c.origem}-${c.fornecedor_id ?? c.empresa_rede_tenant_id}`}
              className="flex items-start justify-between gap-2 border-b border-border py-1"
            >
              <span>
                <Badge>{c.origem === "NETWORK" ? "Rede" : "Cadastro"}</Badge>{" "}
                <span className="text-text">{c.nome}</span>{" "}
                <span className="text-muted">
                  aderência {Math.round(c.pontuacao * 100)}% ·{" "}
                  {c.motivos.join(" ")}
                </span>
              </span>
              <button
                type="button"
                className="text-cyan"
                disabled={ocupado}
                onClick={() =>
                  executar(async () => {
                    await api.post(
                      `${url}/participantes`,
                      c.origem === "NETWORK"
                        ? { empresa_rede_tenant_id: c.empresa_rede_tenant_id }
                        : { fornecedor_id: c.fornecedor_id },
                    );
                    setCandidatos((atual) =>
                      (atual ?? []).filter((x) => x !== c),
                    );
                  })
                }
              >
                Convidar
              </button>
            </div>
          ))}
          {candidatos?.length === 0 && (
            <div className="text-muted">Nenhum candidato com aderência.</div>
          )}
        </div>
        <form
          className="mt-2 flex gap-2"
          onSubmit={formulario((form) =>
            api.post(`${url}/participantes`, {
              nome: String(form.get("nome")),
            }),
          )}
        >
          <Input
            name="nome"
            required
            placeholder="Convidar pelo nome"
            className="flex-1"
          />
          <Button type="submit" size="sm" variant="ghost" disabled={ocupado}>
            Convidar
          </Button>
        </form>
      </Card>
      <Card>
        <SectionLabel>Participantes</SectionLabel>
        <div className="flex flex-col gap-1.5 text-[11px]">
          {ws.participantes.map((p) => (
            <form
              key={p.id}
              className="flex flex-wrap items-center gap-2 border-b border-border py-1"
              onSubmit={formulario((form) =>
                api.put(`${url}/participantes/${p.id}`, {
                  status: String(form.get("status")),
                  motivo: texto(form, "motivo"),
                }),
              )}
            >
              <span className="flex-1 text-text">
                {p.nome}{" "}
                <Badge>{ROTULO_PARTICIPANTE[p.status] ?? p.status}</Badge>
                {p.historico && p.historico.processos > 0 && (
                  <span className="block text-[10px] text-muted">
                    Histórico: {p.historico.processos} processo(s), respondeu{" "}
                    {p.historico.respondeu}, venceu {p.historico.adjudicado},
                    declinou {p.historico.declinou}
                    {p.historico.desqualificado > 0 &&
                      `, desqualificado ${p.historico.desqualificado}`}
                  </span>
                )}
              </span>
              {!fluxo.final && (
                <>
                  <Select name="status" className="w-36">
                    <option value="QUALIFICADO">Qualificar</option>
                    <option value="SHORTLIST">Shortlist</option>
                    <option value="DESQUALIFICADO">Desqualificar</option>
                    <option value="DECLINOU">Declinou</option>
                  </Select>
                  <Input name="motivo" placeholder="Motivo" className="w-32" />
                  <Button
                    type="submit"
                    size="sm"
                    variant="ghost"
                    disabled={ocupado}
                  >
                    Salvar
                  </Button>
                </>
              )}
              {!fluxo.final &&
                !["DECLINOU", "DESQUALIFICADO"].includes(p.status) && (
                  <button
                    type="button"
                    className="text-cyan"
                    disabled={ocupado}
                    onClick={() =>
                      executar(async () => {
                        const acesso = await api.post<{ caminho: string }>(
                          `${url}/participantes/${p.id}/acesso`,
                          {},
                        );
                        setLink({
                          participanteId: p.id,
                          url: `${window.location.origin}${acesso.caminho}`,
                        });
                      })
                    }
                  >
                    Link de acesso
                  </button>
                )}
              {link?.participanteId === p.id && (
                <div className="w-full rounded-md border border-border p-1.5 text-[10px]">
                  Envie ao fornecedor (aparece só agora; gerar outro invalida
                  este):{" "}
                  <span
                    className="break-all text-text"
                    data-testid="link-acesso"
                  >
                    {link.url}
                  </span>
                </div>
              )}
              {p.motivo && (
                <div className="w-full text-[10px] text-muted">{p.motivo}</div>
              )}
            </form>
          ))}
          {ws.participantes.length === 0 && (
            <div className="text-muted">Nenhum participante.</div>
          )}
        </div>
      </Card>
      {ws.esclarecimentos.length > 0 && (
        <Card className="lg:col-span-2">
          <SectionLabel>
            Esclarecimentos (a resposta vai para todos, sem dizer quem
            perguntou)
          </SectionLabel>
          {ws.esclarecimentos.map((e) => (
            <form
              key={e.id}
              className="flex flex-wrap items-center gap-2 border-b border-border py-1 text-[11px]"
              onSubmit={formulario((form) =>
                api.put(`/sourcing/esclarecimentos/${e.id}`, {
                  resposta: String(form.get("resposta") ?? ""),
                }),
              )}
            >
              <span className="flex-1">
                <span className="text-muted">
                  {nomeParticipante(e.participante_id)}:
                </span>{" "}
                {e.pergunta}
                {e.resposta && (
                  <div className="text-muted">Resposta: {e.resposta}</div>
                )}
              </span>
              {!e.resposta && (
                <>
                  <Input
                    name="resposta"
                    required
                    placeholder="Resposta"
                    className="w-64"
                  />
                  <Button
                    type="submit"
                    size="sm"
                    variant="ghost"
                    disabled={ocupado}
                  >
                    Responder
                  </Button>
                </>
              )}
            </form>
          ))}
        </Card>
      )}
    </div>
  );

  const perguntas = vigentes.filter((r) => r.categoria === "PERGUNTA");
  const avaliaveis = vigentes.filter((r) => r.categoria !== "PERGUNTA");
  const emAvaliacao = ["EM_AVALIACAO", "EM_NEGOCIACAO"].includes(
    processo.status,
  );
  const propostas = (
    <div className="flex flex-col gap-3.5">
      {emAvaliacao && avaliaveis.length > 0 && ws.propostas.length > 0 && (
        <SugerirAvaliacao
          url={url}
          ocupado={ocupado}
          executar={executar}
          aoReceber={setSugestoes}
        />
      )}
      {fluxo.recebe_propostas && (
        <Card>
          <SectionLabel>
            Registrar{" "}
            {processo.tipo_processo === "RFI" ? "resposta" : "proposta"}{" "}
            recebida
          </SectionLabel>
          <form
            className="flex flex-wrap gap-2"
            onSubmit={formulario((form) =>
              api.post(`${url}/propostas`, {
                participante_id: Number(form.get("participante_id")),
                ...lerProposta(form, ws.itens, perguntas),
              }),
            )}
          >
            <Select name="participante_id" className="w-44">
              {ws.participantes.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.nome}
                </option>
              ))}
            </Select>
            <CamposProposta
              itens={ws.itens}
              respostas={perguntas}
              valorTotal={!fluxo.com_itens}
            />
            <Button type="submit" size="sm" disabled={ocupado}>
              Registrar
            </Button>
          </form>
        </Card>
      )}
      {ws.propostas.map((p) => (
        <Card key={p.id}>
          <SectionLabel>
            {nomeParticipante(p.participante_id)} · rodada {p.rodada}
          </SectionLabel>
          <div className="text-[11px] text-muted">
            {dinheiro(p.valor_total)} · {p.prazo_entrega_dias ?? "—"} dias ·{" "}
            {p.condicoes_pagamento ?? "pagamento não informado"}
            {p.canal === "PORTAL" && " · enviada pelo fornecedor"}
          </div>
          {ws.anexos
            .filter((a) => a.proposta_id === p.id)
            .map((a) => (
              <button
                key={a.id}
                type="button"
                className="mr-2 text-[11px] text-cyan"
                onClick={() =>
                  executar(async () => {
                    const blob = await getBlob(`/sourcing/anexos/${a.id}`);
                    const ancora = document.createElement("a");
                    ancora.href = URL.createObjectURL(blob);
                    ancora.download = a.nome_arquivo;
                    ancora.click();
                    URL.revokeObjectURL(ancora.href);
                  })
                }
              >
                📎 {a.nome_arquivo}
              </button>
            ))}
          <div className="mt-2 flex flex-col gap-1 text-[11px]">
            {p.avaliacoes
              .filter((a) => a.resposta)
              .map((a) => (
                <div key={`r-${a.requisito_id}`} className="text-muted">
                  {ws.requisitos.find((r) => r.id === a.requisito_id)?.texto}:{" "}
                  <i>{a.resposta}</i>
                </div>
              ))}
            {avaliaveis.map((r) => {
              const atual = p.avaliacoes.find((a) => a.requisito_id === r.id);
              const sugestao = sugestoes.find(
                (x) => x.proposta_id === p.id && x.requisito_id === r.id,
              );
              return (
                <form
                  key={r.id}
                  className="flex flex-wrap items-center gap-2"
                  onSubmit={formulario((form) =>
                    api.put(`/sourcing/propostas/${p.id}/avaliacoes`, {
                      requisito_id: r.id,
                      status: String(form.get("status")),
                      nota: numero(form, "nota"),
                      justificativa: texto(form, "justificativa"),
                    }),
                  )}
                >
                  <span className="flex-1">
                    {r.texto}{" "}
                    {r.obrigatorio && <Badge tone="violet">Obrigatório</Badge>}
                    {sugestao && (
                      <span
                        className="block text-muted"
                        data-testid="sugestao-ia"
                      >
                        IA sugere <Badge tone="cyan">{sugestao.status}</Badge> “
                        {sugestao.citacao}”{" "}
                        <button
                          type="button"
                          className="text-cyan"
                          disabled={ocupado}
                          onClick={() =>
                            executar(() =>
                              api.put(
                                `/sourcing/propostas/${p.id}/avaliacoes`,
                                {
                                  requisito_id: r.id,
                                  status: sugestao.status,
                                  nota: null,
                                  justificativa: `Evidência na proposta: “${sugestao.citacao}”`,
                                },
                              ),
                            )
                          }
                        >
                          Aplicar
                        </button>
                      </span>
                    )}
                  </span>
                  <Select
                    name="status"
                    defaultValue={atual?.status ?? "UNKNOWN"}
                    className="w-44"
                  >
                    {STATUS_AVALIACAO.map((s) => (
                      <option key={s} value={s}>
                        {s}
                      </option>
                    ))}
                  </Select>
                  <Input
                    name="nota"
                    type="number"
                    min={0}
                    max={10}
                    step="0.5"
                    defaultValue={atual?.nota ?? ""}
                    placeholder="Nota"
                    className="w-16"
                  />
                  <Input
                    name="justificativa"
                    placeholder="Justificativa"
                    className="w-40"
                  />
                  <Button
                    type="submit"
                    size="sm"
                    variant="ghost"
                    disabled={ocupado}
                  >
                    Avaliar
                  </Button>
                </form>
              );
            })}
          </div>
        </Card>
      ))}
      {ws.propostas.length === 0 && (
        <div className="text-[12px] text-muted">
          Nenhuma proposta registrada.
        </div>
      )}
    </div>
  );

  const comparacaoAba = (
    <Card>
      <SectionLabel>Comparação de propostas</SectionLabel>
      <div className="text-[10px] text-muted">{comparacao?.aviso}</div>
      <div className="mt-2 overflow-x-auto">
        <table className="w-full text-left text-[11px]">
          <thead className="text-muted">
            <tr>
              <th className="py-1">Participante</th>
              <th>Rodada</th>
              <th>Obrigatórios</th>
              <th>Nota ponderada</th>
              <th>Valor</th>
              <th>Prazo</th>
              <th>Pagamento</th>
              <th>Risco</th>
            </tr>
          </thead>
          <tbody>
            {(comparacao?.linhas ?? []).map((l) => (
              <tr key={l.participante_id} className="border-t border-border">
                <td className="py-1 text-text">
                  {l.participante}{" "}
                  {comparacao?.destaques.menor_valor === l.participante_id && (
                    <Badge tone="green">menor valor</Badge>
                  )}{" "}
                  {comparacao?.destaques.maior_nota === l.participante_id && (
                    <Badge tone="cyan">maior nota</Badge>
                  )}
                </td>
                <td>{l.rodada}</td>
                <td>
                  {l.tecnico.obrigatorios_atendidos}/{l.tecnico.obrigatorios}
                </td>
                <td>{l.tecnico.nota_ponderada ?? "—"}</td>
                <td>{dinheiro(l.comercial.valor_total)}</td>
                <td>{l.comercial.prazo_entrega_dias ?? "—"}</td>
                <td>{l.comercial.condicoes_pagamento ?? "—"}</td>
                <td className="text-red">{l.risco ?? ""}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );

  return (
    <ProcessWorkspace
      testId="sourcing-workspace"
      voltar={{ para: "/sourcing", rotulo: "Strategic Sourcing" }}
      titulo={processo.titulo}
      subtitulo={`${TIPOS_SOURCING[processo.tipo_processo] ?? processo.tipo_processo} · ${ROTULO_STATUS_SOURCING[processo.status] ?? processo.status}`}
      avisos={erro && <div className="text-[12px] text-red">{erro}</div>}
      abas={[
        {
          id: "visao",
          rotulo: "Visão geral",
          conteudo: (
            <div className="flex flex-col gap-3.5">
              <PainelInteligencia
                inteligencia={ws.inteligencia}
                nomeParticipante={nomeParticipante}
              />
              {andamento}
            </div>
          ),
        },
        {
          id: "requisitos",
          rotulo: fluxo.com_itens ? "Itens e requisitos" : "Requisitos",
          conteudo: requisitos,
        },
        {
          id: "fornecedores",
          rotulo: "Fornecedores",
          conteudo: fornecedores,
          contador: ws.participantes.length,
        },
        {
          id: "propostas",
          rotulo: processo.tipo_processo === "RFI" ? "Respostas" : "Propostas",
          conteudo: propostas,
          contador: ws.propostas.length,
        },
        {
          id: "comparacao",
          rotulo: "Comparação",
          conteudo: comparacaoAba,
          visivel: ["RFI", "EOI"].indexOf(processo.tipo_processo) === -1,
        },
      ]}
    />
  );
}
