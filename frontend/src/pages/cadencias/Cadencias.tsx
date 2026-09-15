import { useEffect, useState, type FormEvent } from "react";
import { useSearchParams } from "react-router-dom";

import { AvisoWhatsAppTemplate } from "@/components/AvisoWhatsAppTemplate";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, SectionLabel } from "@/components/ui/Card";
import { Input, Select } from "@/components/ui/Input";
import { Modal } from "@/components/ui/Modal";
import type { Conta, ICP, ListaProspeccao } from "@/pages/prospeccao/Prospeccao";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";

interface Cadencia {
  id: number;
  nome: string;
  canais: string[];
  status: "rascunho" | "aguardando_aprovacao" | "ativa" | "cancelada";
  tipo: string;
  data_inicio: string | null;
  icp_id: number | null;
  oferta_id: number | null;
}

interface OfertaResumo {
  id: number;
  nome: string;
}

interface TemplateWhatsApp {
  id: number;
  nome: string;
  status: string;
}

interface ToqueCadencia {
  id: number;
  ordem: number;
  canal: string;
  intervalo_dias_apos_anterior: number;
  template_whatsapp_id: string | null;
  ab_teste_habilitado: boolean;
}

interface ToqueRascunho {
  ordem: number;
  canal: string;
  intervalo_dias_apos_anterior: number;
  template_whatsapp_id: string;
  ab_teste_habilitado: boolean;
}

interface GerarLoteResultado {
  contas_processadas: number[];
  contas_sem_decisor: number[];
  mensagens_geradas: number;
  toques_bloqueados_restricao: number;
  toques_falha_ia: number;
}

// Mesmo limite de app/services/cadencia_service.py::MAXIMO_CONTAS_POR_LOTE —
// cada toque gerado é uma chamada síncrona à IA na mesma requisição; um
// lote grande de uma vez estourava o tempo de conexão antes de terminar
// (bug real de produção). Em vez de forçar a pessoa a fatiar a seleção
// na mão, a tela quebra automaticamente em lotes desse tamanho.
const MAXIMO_CONTAS_POR_LOTE = 4;

function paraLotes<T>(itens: T[], tamanho: number): T[][] {
  const lotes: T[][] = [];
  for (let i = 0; i < itens.length; i += tamanho) {
    lotes.push(itens.slice(i, i + tamanho));
  }
  return lotes;
}

function toqueVazio(ordem: number, canal: string): ToqueRascunho {
  return { ordem, canal, intervalo_dias_apos_anterior: ordem === 1 ? 0 : 2, template_whatsapp_id: "", ab_teste_habilitado: false };
}

function toneStatus(status: string): "cyan" | "amber" | "green" | "muted" {
  if (status === "ativa") return "green";
  if (status === "aguardando_aprovacao") return "amber";
  if (status === "cancelada") return "muted";
  return "cyan";
}

export function Cadencias() {
  const { usuario } = useAuth();
  const permiteAbTeste = usuario?.recursos_plano.ab_teste_cadencia ?? false;
  const [searchParams] = useSearchParams();
  const cadenciaIdDaUrl = Number(searchParams.get("cadencia_id")) || null;
  const [cadencias, setCadencias] = useState<Cadencia[]>([]);
  const [cadenciaSelecionadaId, setCadenciaSelecionadaId] = useState<number | null>(null);
  const [toques, setToques] = useState<ToqueCadencia[]>([]);
  const [icps, setIcps] = useState<ICP[]>([]);
  const [ofertas, setOfertas] = useState<OfertaResumo[]>([]);
  const [icpParaCriacaoId, setIcpParaCriacaoId] = useState<number | null>(null);
  const [listas, setListas] = useState<ListaProspeccao[]>([]);
  const [templatesWhatsapp, setTemplatesWhatsapp] = useState<TemplateWhatsApp[]>([]);
  const [origemLote, setOrigemLote] = useState<"icp" | "lista" | "leads">("icp");
  const [icpParaLoteId, setIcpParaLoteId] = useState<number | null>(null);
  const [listaParaLoteId, setListaParaLoteId] = useState<number | null>(null);
  const [contasDoIcp, setContasDoIcp] = useState<Conta[]>([]);
  const [contasSelecionadas, setContasSelecionadas] = useState<Set<number>>(new Set());
  const [modalCriarAberto, setModalCriarAberto] = useState(false);
  const [rascunhoToques, setRascunhoToques] = useState<ToqueRascunho[]>([
    toqueVazio(1, "email"),
    toqueVazio(2, "whatsapp"),
    toqueVazio(3, "email"),
    toqueVazio(4, "linkedin"),
    toqueVazio(5, "whatsapp"),
  ]);
  const [resultadoGeracao, setResultadoGeracao] = useState<GerarLoteResultado | null>(null);
  const [progressoGeracao, setProgressoGeracao] = useState<{ atual: number; total: number } | null>(null);
  const [confirmandoExclusao, setConfirmandoExclusao] = useState(false);
  const [confirmandoCancelamento, setConfirmandoCancelamento] = useState(false);
  const [cancelando, setCancelando] = useState(false);
  const [editandoNome, setEditandoNome] = useState(false);
  const [nomeEditavel, setNomeEditavel] = useState("");
  const [salvandoNome, setSalvandoNome] = useState(false);
  const [novoToqueCanal, setNovoToqueCanal] = useState("email");
  const [novoToqueIntervalo, setNovoToqueIntervalo] = useState(2);
  const [novoToqueTemplateId, setNovoToqueTemplateId] = useState("");
  const [adicionandoToque, setAdicionandoToque] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [mensagem, setMensagem] = useState<string | null>(null);

  const cadenciaSelecionada = cadencias.find((c) => c.id === cadenciaSelecionadaId) ?? null;

  async function carregarCadencias() {
    try {
      const resposta = await api.get<Cadencia[]>("/cadencias");
      setCadencias(resposta);
      if (cadenciaSelecionadaId === null) {
        // Prioriza `?cadencia_id=` (ex.: veio da busca global); sem ele,
        // cai no comportamento de sempre (seleciona a primeira da lista).
        const daUrl = cadenciaIdDaUrl && resposta.find((c) => c.id === cadenciaIdDaUrl);
        if (daUrl) setCadenciaSelecionadaId(daUrl.id);
        else if (resposta.length > 0) setCadenciaSelecionadaId(resposta[0].id);
      }
    } catch {
      setErro("Não foi possível carregar as cadências.");
    }
  }

  async function carregarIcps() {
    try {
      const resposta = await api.get<ICP[]>("/icp");
      setIcps(resposta);
    } catch {
      setErro("Não foi possível carregar os ICPs.");
    }
  }

  async function carregarListas() {
    try {
      setListas(await api.get<ListaProspeccao[]>("/listas-prospeccao"));
    } catch {
      setErro("Não foi possível carregar as listas de prospecção.");
    }
  }

  async function carregarOfertas() {
    try {
      setOfertas(await api.get<OfertaResumo[]>("/ofertas"));
    } catch {
      setErro("Não foi possível carregar as ofertas.");
    }
  }

  useEffect(() => {
    carregarCadencias();
    carregarIcps();
    carregarOfertas();
    carregarListas();
    // Sincroniza com a Meta a cada carregamento (mesmo padrão de
    // Campanhas.tsx) — um template recém-aprovado já aparece aqui sem
    // precisar de nenhum botão de "atualizar" separado.
    api
      .get<TemplateWhatsApp[]>("/whatsapp/templates")
      .then((resposta) => setTemplatesWhatsapp(resposta.filter((template) => template.status === "aprovado")))
      .catch(() => undefined);
  }, []);

  async function carregarToques(cadenciaId: number) {
    try {
      setToques(await api.get<ToqueCadencia[]>(`/cadencias/${cadenciaId}/toques`));
    } catch {
      setErro("Não foi possível carregar os toques da cadência.");
    }
  }

  useEffect(() => {
    if (cadenciaSelecionadaId === null) return;
    setResultadoGeracao(null);
    carregarToques(cadenciaSelecionadaId);
  }, [cadenciaSelecionadaId]);

  async function definirTemplateWhatsapp(toqueId: number, templateId: string) {
    if (cadenciaSelecionadaId === null || !templateId) return;
    try {
      await api.put(`/cadencias/${cadenciaSelecionadaId}/toques/${toqueId}/template-whatsapp`, {
        template_whatsapp_id: templateId,
      });
      await carregarToques(cadenciaSelecionadaId);
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível definir o template deste toque.");
    }
  }

  useEffect(() => {
    setContasSelecionadas(new Set());
    if (origemLote === "leads") {
      api
        .get<Conta[]>("/leads/contas")
        .then(setContasDoIcp)
        .catch(() => setErro("Não foi possível carregar os clientes cadastrados."));
      return;
    }
    if (origemLote === "lista") {
      if (listaParaLoteId === null) {
        setContasDoIcp([]);
        return;
      }
      api
        .get<Conta[]>(`/listas-prospeccao/${listaParaLoteId}/contas`)
        .then(setContasDoIcp)
        .catch(() => setErro("Não foi possível carregar as contas da lista."));
      return;
    }
    if (icpParaLoteId === null) {
      setContasDoIcp([]);
      return;
    }
    api
      .get<Conta[]>(`/icp/${icpParaLoteId}/contas`)
      .then(setContasDoIcp)
      .catch(() => setErro("Não foi possível carregar as contas do ICP."));
  }, [icpParaLoteId, listaParaLoteId, origemLote]);

  function atualizarToque(indice: number, campo: keyof ToqueRascunho, valor: string | boolean) {
    setRascunhoToques((atual) =>
      atual.map((toque, i) => (i === indice ? { ...toque, [campo]: valor } : toque)),
    );
  }

  function adicionarToque() {
    setRascunhoToques((atual) => [...atual, toqueVazio(atual.length + 1, "email")]);
  }

  function removerToque(indice: number) {
    setRascunhoToques((atual) =>
      atual.filter((_, i) => i !== indice).map((toque, i) => ({ ...toque, ordem: i + 1 })),
    );
  }

  async function criarCadencia(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    try {
      await api.post("/cadencias", {
        nome: String(form.get("nome")),
        tipo: String(form.get("tipo")),
        icp_id: icpParaCriacaoId,
        toques: rascunhoToques.map((toque) => ({
          ordem: toque.ordem,
          canal: toque.canal,
          intervalo_dias_apos_anterior: Number(toque.intervalo_dias_apos_anterior),
          template_whatsapp_id: toque.canal === "whatsapp" ? toque.template_whatsapp_id || null : null,
          ab_teste_habilitado: toque.ab_teste_habilitado,
        })),
      });
      setModalCriarAberto(false);
      setIcpParaCriacaoId(null);
      setRascunhoToques([
        toqueVazio(1, "email"),
        toqueVazio(2, "whatsapp"),
        toqueVazio(3, "email"),
        toqueVazio(4, "linkedin"),
        toqueVazio(5, "whatsapp"),
      ]);
      await carregarCadencias();
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível criar a cadência.");
    }
  }

  function alternarConta(contaId: number) {
    setContasSelecionadas((atual) => {
      const nova = new Set(atual);
      if (nova.has(contaId)) nova.delete(contaId);
      else nova.add(contaId);
      return nova;
    });
  }

  function alternarTodasAsContas() {
    setContasSelecionadas((atual) =>
      atual.size === contasDoIcp.length ? new Set() : new Set(contasDoIcp.map((conta) => conta.id)),
    );
  }

  async function gerarParaLote() {
    if (cadenciaSelecionadaId === null || contasSelecionadas.size === 0) return;
    setErro(null);
    setResultadoGeracao(null);

    const lotes = paraLotes(Array.from(contasSelecionadas), MAXIMO_CONTAS_POR_LOTE);
    const acumulado: GerarLoteResultado = {
      contas_processadas: [],
      contas_sem_decisor: [],
      mensagens_geradas: 0,
      toques_bloqueados_restricao: 0,
      toques_falha_ia: 0,
    };

    try {
      for (let i = 0; i < lotes.length; i++) {
        setProgressoGeracao({ atual: i + 1, total: lotes.length });
        const resultado = await api.post<GerarLoteResultado>(`/cadencias/${cadenciaSelecionadaId}/gerar`, {
          conta_ids: lotes[i],
        });
        acumulado.contas_processadas.push(...resultado.contas_processadas);
        acumulado.contas_sem_decisor.push(...resultado.contas_sem_decisor);
        acumulado.mensagens_geradas += resultado.mensagens_geradas ?? 0;
        // `?? 0` — API antiga (antes deste campo existir) responde sem essa
        // chave; sem a defesa, `acumulado + undefined = NaN` propaga pro
        // resto da soma e o aviso de "N toque(s) bloqueados" nunca aparece
        // (raio-X: `NaN > 0` é `false`), mascarando o problema real por
        // trás de uma tela que parece só "gerou 0 mensagens" sem explicar.
        acumulado.toques_bloqueados_restricao += resultado.toques_bloqueados_restricao ?? 0;
        acumulado.toques_falha_ia += resultado.toques_falha_ia ?? 0;
      }
      setResultadoGeracao(acumulado);
      setContasSelecionadas(new Set());
      await carregarCadencias();
    } catch (error) {
      // Lotes já concluídos ficam salvos (cada mensagem é gravada assim que
      // gerada) — mostra o que já deu certo antes do lote que falhou.
      setResultadoGeracao(acumulado);
      setErro(error instanceof ApiError ? error.message : "Não foi possível gerar as mensagens.");
    } finally {
      setProgressoGeracao(null);
    }
  }

  async function ativarCadencia() {
    if (cadenciaSelecionadaId === null) return;
    setErro(null);
    try {
      await api.post(`/cadencias/${cadenciaSelecionadaId}/ativar`);
      setMensagem("Cadência ativada — os envios entram na fila conforme o agendamento de cada toque.");
      await carregarCadencias();
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível ativar a cadência.");
    }
  }

  async function excluirCadencia() {
    if (cadenciaSelecionadaId === null) return;
    setErro(null);
    try {
      await api.delete(`/cadencias/${cadenciaSelecionadaId}`);
      setConfirmandoExclusao(false);
      setCadenciaSelecionadaId(null);
      setMensagem("Cadência excluída.");
      await carregarCadencias();
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível excluir a cadência.");
    }
  }

  async function cancelarCadencia() {
    if (cadenciaSelecionadaId === null || cancelando) return;
    setCancelando(true);
    setErro(null);
    try {
      const resultado = await api.post<{ mensagens_canceladas: number }>(
        `/cadencias/${cadenciaSelecionadaId}/cancelar`,
      );
      setConfirmandoCancelamento(false);
      setMensagem(
        `Cadência cancelada — ${resultado.mensagens_canceladas} mensagem(ns) que ainda não tinham saído foram canceladas. As já enviadas continuam no histórico.`,
      );
      await carregarCadencias();
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível cancelar a cadência.");
    } finally {
      setCancelando(false);
    }
  }

  function iniciarEdicaoNome() {
    if (!cadenciaSelecionada) return;
    setNomeEditavel(cadenciaSelecionada.nome);
    setEditandoNome(true);
  }

  async function salvarNome() {
    if (cadenciaSelecionadaId === null || !nomeEditavel.trim() || salvandoNome) return;
    setSalvandoNome(true);
    setErro(null);
    try {
      await api.put(`/cadencias/${cadenciaSelecionadaId}`, { nome: nomeEditavel.trim() });
      setEditandoNome(false);
      await carregarCadencias();
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível renomear a cadência.");
    } finally {
      setSalvandoNome(false);
    }
  }

  async function adicionarToqueReal() {
    if (cadenciaSelecionadaId === null || adicionandoToque) return;
    setAdicionandoToque(true);
    setErro(null);
    try {
      await api.post(`/cadencias/${cadenciaSelecionadaId}/toques`, {
        canal: novoToqueCanal,
        intervalo_dias_apos_anterior: Number(novoToqueIntervalo) || 0,
        template_whatsapp_id: novoToqueCanal === "whatsapp" ? novoToqueTemplateId || null : null,
      });
      setNovoToqueCanal("email");
      setNovoToqueIntervalo(2);
      setNovoToqueTemplateId("");
      await carregarToques(cadenciaSelecionadaId);
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível adicionar o toque.");
    } finally {
      setAdicionandoToque(false);
    }
  }

  async function atualizarToqueReal(toqueId: number, campo: "canal" | "intervalo_dias_apos_anterior", valor: string) {
    if (cadenciaSelecionadaId === null) return;
    try {
      await api.put(`/cadencias/${cadenciaSelecionadaId}/toques/${toqueId}`, {
        [campo]: campo === "intervalo_dias_apos_anterior" ? Number(valor) || 0 : valor,
      });
      await carregarToques(cadenciaSelecionadaId);
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível atualizar o toque.");
    }
  }

  async function removerToqueReal(toqueId: number) {
    if (cadenciaSelecionadaId === null) return;
    setErro(null);
    try {
      await api.delete(`/cadencias/${cadenciaSelecionadaId}/toques/${toqueId}`);
      await carregarToques(cadenciaSelecionadaId);
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível remover o toque.");
    }
  }

  return (
    <div className="p-5.5">
      <AvisoWhatsAppTemplate />
      <div className="mb-5 flex items-end justify-between">
        <div>
          <div className="font-head text-xl font-bold">Cadências</div>
          <div className="mt-0.5 text-[11px] text-muted">
            Sequência de toques multicanal gerada por IA, mediante aprovação
          </div>
        </div>
        <Button size="sm" variant="violet" onClick={() => setModalCriarAberto(true)}>
          + Nova cadência
        </Button>
      </div>

      {erro && <div className="mb-4 text-[12px] text-red">{erro}</div>}
      {mensagem && <div className="mb-4 text-[12px] text-green">{mensagem}</div>}

      <Card className="mb-4">
        <SectionLabel>Cadências</SectionLabel>
        <div className="flex flex-wrap gap-2">
          {cadencias.map((cadencia) => (
            <button
              key={cadencia.id}
              onClick={() => {
                setCadenciaSelecionadaId(cadencia.id);
                setConfirmandoExclusao(false);
              }}
              className={`rounded-lg border px-3 py-1.5 text-[12px] ${
                cadencia.id === cadenciaSelecionadaId
                  ? "border-cyan bg-cyan/15 text-cyan"
                  : "border-border text-muted hover:text-text"
              }`}
            >
              {cadencia.nome}
            </button>
          ))}
          {cadencias.length === 0 && <div className="text-[12px] text-muted">Nenhuma cadência criada ainda.</div>}
        </div>
      </Card>

      {cadenciaSelecionada && (
        <>
          <Card className="mb-4">
            <div className="mb-2 flex items-center justify-between">
              {editandoNome ? (
                <div className="flex flex-1 items-center gap-1.5">
                  <Input
                    value={nomeEditavel}
                    onChange={(event) => setNomeEditavel(event.target.value)}
                    className="max-w-xs"
                    autoFocus
                  />
                  <Button size="sm" disabled={salvandoNome} onClick={salvarNome}>
                    {salvandoNome ? "Salvando..." : "Salvar"}
                  </Button>
                  <Button size="sm" variant="ghost" onClick={() => setEditandoNome(false)}>
                    Cancelar
                  </Button>
                </div>
              ) : (
                <div className="flex items-center gap-1.5">
                  <SectionLabel>{cadenciaSelecionada.nome}</SectionLabel>
                  <button
                    type="button"
                    onClick={iniciarEdicaoNome}
                    title="Renomear cadência"
                    className="text-[11px] text-muted hover:text-cyan"
                  >
                    ✎
                  </button>
                </div>
              )}
              <div className="flex items-center gap-2">
                <Badge tone={toneStatus(cadenciaSelecionada.status)}>{cadenciaSelecionada.status}</Badge>
                {(cadenciaSelecionada.status === "aguardando_aprovacao" || cadenciaSelecionada.status === "ativa") && (
                  <Button size="sm" onClick={ativarCadencia}>
                    {cadenciaSelecionada.status === "ativa" ? "Agendar novas mensagens" : "Ativar cadência"}
                  </Button>
                )}
                {cadenciaSelecionada.status === "rascunho" && !confirmandoExclusao && (
                  <Button size="sm" variant="danger" onClick={() => setConfirmandoExclusao(true)}>
                    Excluir
                  </Button>
                )}
                {confirmandoExclusao && (
                  <>
                    <span className="text-[11px] text-muted">Excluir esta cadência?</span>
                    <Button size="sm" variant="danger" onClick={excluirCadencia}>
                      Confirmar
                    </Button>
                    <Button size="sm" variant="ghost" onClick={() => setConfirmandoExclusao(false)}>
                      Cancelar
                    </Button>
                  </>
                )}
                {(cadenciaSelecionada.status === "aguardando_aprovacao" || cadenciaSelecionada.status === "ativa") &&
                  !confirmandoCancelamento && (
                    <Button size="sm" variant="danger" onClick={() => setConfirmandoCancelamento(true)}>
                      Cancelar cadência
                    </Button>
                  )}
                {confirmandoCancelamento && (
                  <>
                    <span className="text-[11px] text-muted">
                      Cancelar esta cadência? Mensagens já enviadas continuam no histórico; as pendentes deixam de
                      sair.
                    </span>
                    <Button size="sm" variant="danger" disabled={cancelando} onClick={cancelarCadencia}>
                      {cancelando ? "Cancelando..." : "Confirmar"}
                    </Button>
                    <Button size="sm" variant="ghost" onClick={() => setConfirmandoCancelamento(false)}>
                      Voltar
                    </Button>
                  </>
                )}
              </div>
            </div>
            <div className="mb-2 text-[11px] text-muted">
              Campanha: {ofertas.find((o) => o.id === cadenciaSelecionada.oferta_id)?.nome ?? "—"} · ICP:{" "}
              {icps.find((i) => i.id === cadenciaSelecionada.icp_id)?.nome ?? "—"}
            </div>
            <div className="flex flex-col gap-1.5">
              {toques.map((toque) => (
                <div key={toque.id} className="flex flex-wrap items-center gap-2 text-[12px] text-muted">
                  <span className="font-head font-bold text-text">#{toque.ordem}</span>
                  {cadenciaSelecionada.status === "cancelada" ? (
                    <Badge tone="cyan">{toque.canal}</Badge>
                  ) : (
                    <Select
                      className="w-28 flex-shrink-0 text-[11px]"
                      value={toque.canal}
                      onChange={(event) => atualizarToqueReal(toque.id, "canal", event.target.value)}
                    >
                      <option value="email">E-mail</option>
                      <option value="whatsapp">WhatsApp</option>
                      <option value="linkedin">LinkedIn</option>
                    </Select>
                  )}
                  {toque.ordem === 1 ? (
                    <span>imediato</span>
                  ) : cadenciaSelecionada.status === "cancelada" ? (
                    <span>{toque.intervalo_dias_apos_anterior}d depois do anterior</span>
                  ) : (
                    <span className="flex items-center gap-1">
                      <Input
                        type="number"
                        min={0}
                        value={toque.intervalo_dias_apos_anterior}
                        onChange={(event) => atualizarToqueReal(toque.id, "intervalo_dias_apos_anterior", event.target.value)}
                        className="w-16 flex-shrink-0"
                      />
                      d depois do anterior
                    </span>
                  )}
                  {toque.canal === "whatsapp" &&
                    (toque.template_whatsapp_id ? (
                      <>
                        <Badge tone="cyan">
                          template:{" "}
                          {templatesWhatsapp.find((t) => String(t.id) === toque.template_whatsapp_id)?.nome ??
                            toque.template_whatsapp_id}
                        </Badge>
                        {templatesWhatsapp.length > 0 && cadenciaSelecionada.status !== "cancelada" && (
                          <Select
                            className="w-auto flex-shrink-0 text-[11px]"
                            value={toque.template_whatsapp_id}
                            onChange={(event) => definirTemplateWhatsapp(toque.id, event.target.value)}
                            title="Trocar o template"
                          >
                            {templatesWhatsapp.map((template) => (
                              <option key={template.id} value={template.id}>
                                {template.nome}
                              </option>
                            ))}
                          </Select>
                        )}
                      </>
                    ) : templatesWhatsapp.length > 0 && cadenciaSelecionada.status !== "cancelada" ? (
                      <>
                        <Badge tone="red">sem template — 1º contato fica parado</Badge>
                        <Select
                          className="w-auto flex-shrink-0 text-[11px]"
                          value=""
                          onChange={(event) => definirTemplateWhatsapp(toque.id, event.target.value)}
                        >
                          <option value="" disabled>
                            Definir template aprovado
                          </option>
                          {templatesWhatsapp.map((template) => (
                            <option key={template.id} value={template.id}>
                              {template.nome}
                            </option>
                          ))}
                        </Select>
                      </>
                    ) : (
                      <Badge tone="red">sem template — 1º contato fica parado</Badge>
                    ))}
                  {toque.ab_teste_habilitado && <Badge tone="amber">teste A/B</Badge>}
                  {cadenciaSelecionada.status !== "cancelada" && (
                    <button
                      type="button"
                      className="text-[11px] text-muted hover:text-red"
                      title="Remover toque"
                      onClick={() => removerToqueReal(toque.id)}
                    >
                      ✕
                    </button>
                  )}
                </div>
              ))}
            </div>

            {cadenciaSelecionada.status !== "cancelada" && (
              <div className="mt-2 flex flex-wrap items-center gap-1.5 border-t border-border pt-2">
                <Select
                  className="w-28 flex-shrink-0 text-[11px]"
                  value={novoToqueCanal}
                  onChange={(event) => setNovoToqueCanal(event.target.value)}
                >
                  <option value="email">E-mail</option>
                  <option value="whatsapp">WhatsApp</option>
                  <option value="linkedin">LinkedIn</option>
                </Select>
                <Input
                  type="number"
                  min={0}
                  value={novoToqueIntervalo}
                  onChange={(event) => setNovoToqueIntervalo(Number(event.target.value))}
                  title="Dias após o toque anterior"
                  className="w-20 flex-shrink-0"
                />
                {novoToqueCanal === "whatsapp" && templatesWhatsapp.length > 0 && (
                  <Select
                    className="min-w-[160px] flex-1 text-[11px]"
                    value={novoToqueTemplateId}
                    onChange={(event) => setNovoToqueTemplateId(event.target.value)}
                  >
                    <option value="">Selecione o template aprovado</option>
                    {templatesWhatsapp.map((template) => (
                      <option key={template.id} value={template.id}>
                        {template.nome}
                      </option>
                    ))}
                  </Select>
                )}
                <Button size="sm" variant="ghost" disabled={adicionandoToque} onClick={adicionarToqueReal}>
                  {adicionandoToque ? "Adicionando..." : "+ Adicionar toque"}
                </Button>
              </div>
            )}
          </Card>

          {cadenciaSelecionada.status !== "cancelada" && (
            <Card>
              <SectionLabel>Selecionar contas para gerar mensagens</SectionLabel>
              <div className="mb-3 flex gap-2">
                <button
                  type="button"
                  onClick={() => setOrigemLote("icp")}
                  className={`rounded-lg border px-3 py-1.5 text-[12px] ${
                    origemLote === "icp" ? "border-cyan bg-cyan/15 text-cyan" : "border-border text-muted"
                  }`}
                >
                  Por ICP
                </button>
                <button
                  type="button"
                  onClick={() => setOrigemLote("lista")}
                  className={`rounded-lg border px-3 py-1.5 text-[12px] ${
                    origemLote === "lista" ? "border-cyan bg-cyan/15 text-cyan" : "border-border text-muted"
                  }`}
                >
                  Listas de Prospecção
                </button>
                <button
                  type="button"
                  onClick={() => setOrigemLote("leads")}
                  className={`rounded-lg border px-3 py-1.5 text-[12px] ${
                    origemLote === "leads" ? "border-cyan bg-cyan/15 text-cyan" : "border-border text-muted"
                  }`}
                >
                  Clientes Cadastrados
                </button>
              </div>

              {origemLote === "icp" && (
                <div className="mb-3">
                  <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">ICP</div>
                  <Select
                    value={icpParaLoteId ?? ""}
                    onChange={(event) => setIcpParaLoteId(event.target.value ? Number(event.target.value) : null)}
                  >
                    <option value="">Selecione um ICP</option>
                    {icps.map((icp) => (
                      <option key={icp.id} value={icp.id}>
                        {icp.nome} {!icp.ativo && "(inativo)"}
                      </option>
                    ))}
                  </Select>
                </div>
              )}

              {origemLote === "lista" && (
                <div className="mb-3">
                  <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">Lista de Prospecção</div>
                  <Select
                    value={listaParaLoteId ?? ""}
                    onChange={(event) => setListaParaLoteId(event.target.value ? Number(event.target.value) : null)}
                  >
                    <option value="">Selecione uma lista</option>
                    {listas.map((lista) => (
                      <option key={lista.id} value={lista.id}>
                        {lista.nome}
                      </option>
                    ))}
                  </Select>
                  {listas.length === 0 && (
                    <div className="mt-1.5 text-[11px] text-muted">
                      Nenhuma lista de prospecção criada ainda — crie uma na tela de Prospecção.
                    </div>
                  )}
                </div>
              )}

              {contasDoIcp.length > 0 && (
                <div className="mb-3 rounded-lg border border-border">
                  <label className="flex items-center gap-2 border-b border-border p-2 text-[12px] font-semibold">
                    <input
                      type="checkbox"
                      checked={contasSelecionadas.size === contasDoIcp.length}
                      onChange={alternarTodasAsContas}
                    />
                    Selecionar todos ({contasDoIcp.length})
                  </label>
                  <div className="flex max-h-64 flex-col gap-1 overflow-y-auto p-2">
                    {contasDoIcp.map((conta) => (
                      <label key={conta.id} className="flex items-center gap-2 text-[12px]">
                        <input
                          type="checkbox"
                          checked={contasSelecionadas.has(conta.id)}
                          onChange={() => alternarConta(conta.id)}
                        />
                        {conta.nome}
                      </label>
                    ))}
                  </div>
                </div>
              )}
              {contasDoIcp.length === 0 &&
                (origemLote === "leads" ||
                  (origemLote === "icp" && icpParaLoteId !== null) ||
                  (origemLote === "lista" && listaParaLoteId !== null)) && (
                  <div className="mb-3 text-[12px] text-muted">
                    {origemLote === "leads"
                      ? "Nenhum cliente cadastrado ainda."
                      : origemLote === "lista"
                        ? "Nenhuma conta importada para essa lista ainda."
                        : "Nenhuma conta gerada para esse ICP ainda."}
                  </div>
                )}

              <Button disabled={contasSelecionadas.size === 0 || progressoGeracao !== null} onClick={gerarParaLote}>
                {progressoGeracao
                  ? `Gerando lote ${progressoGeracao.atual} de ${progressoGeracao.total}...`
                  : `Gerar mensagens para ${contasSelecionadas.size} conta(s)`}
              </Button>
              {contasSelecionadas.size > MAXIMO_CONTAS_POR_LOTE && !progressoGeracao && (
                <div className="mt-1.5 text-[11px] text-muted">
                  Serão enviadas em {Math.ceil(contasSelecionadas.size / MAXIMO_CONTAS_POR_LOTE)} lotes de até{" "}
                  {MAXIMO_CONTAS_POR_LOTE} contas — cada toque gerado é uma chamada à IA, e lotes menores evitam
                  estourar o tempo de conexão.
                </div>
              )}

              {resultadoGeracao && (
                <div className="mt-3 text-[12px] text-muted">
                  <div>{resultadoGeracao.mensagens_geradas} mensagem(ns) geradas — revise na fila de Aprovações.</div>
                  {resultadoGeracao.contas_sem_decisor.length > 0 && (
                    <div className="mt-1 text-amber">
                      {resultadoGeracao.contas_sem_decisor.length} conta(s) sem decisor mapeado, ficaram de fora —
                      mapeie um decisor na conta antes de tentar de novo.
                    </div>
                  )}
                  {resultadoGeracao.toques_bloqueados_restricao > 0 && (
                    <div className="mt-1 text-amber">
                      {resultadoGeracao.toques_bloqueados_restricao} toque(s) não puderam ser gerados sem violar
                      as restrições configuradas em Configuração → Comunicação — revise a lista de termos
                      proibidos (pode estar bloqueando um termo comum, como o nome da própria empresa/oferta).
                    </div>
                  )}
                  {resultadoGeracao.toques_falha_ia > 0 && (
                    <div className="mt-1 text-amber">
                      {resultadoGeracao.toques_falha_ia} toque(s) não puderam ser gerados por instabilidade da IA
                      (não é problema de configuração) — tente gerar novamente em alguns instantes.
                    </div>
                  )}
                </div>
              )}
            </Card>
          )}
        </>
      )}

      <Modal title="Nova cadência" open={modalCriarAberto} onClose={() => setModalCriarAberto(false)}>
        <form onSubmit={criarCadencia} className="flex flex-col gap-3">
          <div>
            <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">Nome</div>
            <Input name="nome" required placeholder="Ex.: Prospecção clínicas — SP/RJ" />
          </div>
          <div>
            <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">Tipo</div>
            <Select name="tipo" defaultValue="prospeccao">
              <option value="prospeccao">Prospecção</option>
              <option value="nutricao">Nutrição</option>
            </Select>
          </div>

          {icps.filter((icp) => icp.ativo).length > 1 && (
            <div>
              <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">
                ICP desta campanha
              </div>
              <Select
                value={icpParaCriacaoId ?? ""}
                onChange={(event) => setIcpParaCriacaoId(event.target.value ? Number(event.target.value) : null)}
              >
                <option value="">Usar o primeiro ICP ativo</option>
                {icps
                  .filter((icp) => icp.ativo)
                  .map((icp) => (
                    <option key={icp.id} value={icp.id}>
                      {icp.nome}
                    </option>
                  ))}
              </Select>
              <div className="mt-1 text-[11px] text-muted">
                Você tem mais de um ICP ativo — escolha a qual campanha esta cadência pertence, pra não misturar
                o contexto de uma campanha com o de outra na hora de gerar as mensagens.
              </div>
            </div>
          )}

          <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">
            Toques (mínimo 5, em pelo menos 2 canais)
          </div>
          <div className="flex flex-col gap-2">
            {rascunhoToques.map((toque, indice) => (
              <div key={indice} className="flex flex-wrap items-center gap-1.5 rounded-lg border border-border p-2">
                <span className="w-5 flex-shrink-0 text-center text-[11px] text-muted">#{toque.ordem}</span>
                <Select
                  className="w-28 flex-shrink-0"
                  value={toque.canal}
                  onChange={(event) => atualizarToque(indice, "canal", event.target.value)}
                >
                  <option value="email">E-mail</option>
                  <option value="whatsapp">WhatsApp</option>
                  <option value="linkedin">LinkedIn</option>
                </Select>
                {toque.canal === "whatsapp" &&
                  (templatesWhatsapp.length > 0 ? (
                    <Select
                      className="min-w-[180px] flex-1"
                      required
                      value={toque.template_whatsapp_id}
                      onChange={(event) => atualizarToque(indice, "template_whatsapp_id", event.target.value)}
                    >
                      <option value="" disabled>
                        Selecione o template aprovado
                      </option>
                      {templatesWhatsapp.map((template) => (
                        <option key={template.id} value={template.id}>
                          {template.nome}
                        </option>
                      ))}
                    </Select>
                  ) : (
                    <span className="basis-full text-[10.5px] text-amber">
                      ⚠ Nenhum template aprovado ainda — configure em Configuração → WhatsApp Business e crie um
                      template na Meta antes de ativar esta cadência.
                    </span>
                  ))}
                <Input
                  type="number"
                  min={0}
                  value={toque.intervalo_dias_apos_anterior}
                  onChange={(event) => atualizarToque(indice, "intervalo_dias_apos_anterior", event.target.value)}
                  title="Dias após o toque anterior"
                  className="w-20 flex-shrink-0"
                />
                <label
                  className={`flex flex-shrink-0 items-center gap-1 text-[10px] whitespace-nowrap ${
                    permiteAbTeste ? "text-muted" : "text-muted/50"
                  }`}
                  title={permiteAbTeste ? "Testar 2 variantes de mensagem para este toque" : "Requer plano Professional ou superior"}
                >
                  <input
                    type="checkbox"
                    checked={toque.ab_teste_habilitado}
                    disabled={!permiteAbTeste}
                    onChange={(event) => atualizarToque(indice, "ab_teste_habilitado", event.target.checked)}
                  />
                  Teste A/B{!permiteAbTeste && " 🔒"}
                </label>
                <Button type="button" size="sm" variant="danger" onClick={() => removerToque(indice)}>
                  ✕
                </Button>
              </div>
            ))}
          </div>
          <Button type="button" size="sm" variant="ghost" onClick={adicionarToque}>
            + Adicionar toque
          </Button>

          <Button type="submit" className="mt-1 w-full justify-center">
            Criar cadência
          </Button>
        </form>
      </Modal>
    </div>
  );
}
