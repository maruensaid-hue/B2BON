import { useEffect, useState, type FormEvent } from "react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, SectionLabel } from "@/components/ui/Card";
import { Input, Select, Textarea } from "@/components/ui/Input";
import { Modal } from "@/components/ui/Modal";
import type { Conta, ICP } from "@/pages/prospeccao/Prospeccao";
import { TutorialCampanhas } from "@/pages/campanhas/TutorialCampanhas";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";

interface Campanha {
  id: number;
  nome: string;
  tipo: string;
  canais: string[];
  assunto: string | null;
  conteudo_email: string | null;
  template_whatsapp_id: string | null;
  status: "rascunho" | "pronta" | "enviando" | "concluida";
}

interface CampanhaDestinatario {
  id: number;
  decisor_id: number | null;
  nome: string;
  email: string | null;
  telefone: string | null;
  empresa: string | null;
  status: string;
  motivo_falha: string | null;
}

interface CampanhaDetalhe extends Campanha {
  destinatarios: CampanhaDestinatario[];
  metricas: Record<string, number>;
}

interface Decisor {
  id: number;
  nome: string;
  email: string | null;
  telefone: string | null;
}

interface TemplateWhatsApp {
  id: number;
  nome: string;
  status: string;
}

type CampoDestinatario = "nome" | "email" | "telefone" | "empresa";

const SINONIMOS_DESTINATARIO: Record<string, CampoDestinatario> = {
  nome: "nome",
  participante: "nome",
  responsavel: "nome",
  contato: "nome",
  email: "email",
  "e-mail": "email",
  telefone: "telefone",
  fone: "telefone",
  celular: "telefone",
  whatsapp: "telefone",
  empresa: "empresa",
  "razao social": "empresa",
  organizacao: "empresa",
  company: "empresa",
};

function normalizarCabecalho(texto: string): string {
  return texto
    .trim()
    .toLowerCase()
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "");
}

function detectarMapaColunas(primeiraLinha: string, separador: string): CampoDestinatario[] | null {
  const celulas = primeiraLinha.split(separador).map(normalizarCabecalho);
  const mapa = celulas.map((celula) => SINONIMOS_DESTINATARIO[celula]);
  const reconhecidos = mapa.filter(Boolean);
  if (reconhecidos.includes("nome") && (reconhecidos.includes("email") || reconhecidos.includes("telefone"))) {
    return mapa as CampoDestinatario[];
  }
  return null;
}

/** Aceita colar direto do Excel/Planilhas (TAB) ou CSV (`;`/`,`) — uma
 * linha por destinatário. Mesmo mecanismo de detecção de cabeçalho de
 * `Prospeccao.tsx::parseParticipantes`, adaptado sem exigir "empresa". */
function parseDestinatarios(texto: string): { nome: string; email?: string; telefone?: string; empresa?: string }[] {
  const linhas = texto
    .split("\n")
    .map((linha) => linha.trim())
    .filter(Boolean);
  if (linhas.length === 0) return [];

  const separadorDaPrimeira = linhas[0].includes("\t") ? "\t" : linhas[0].includes(";") ? ";" : ",";
  const mapaCabecalho = detectarMapaColunas(linhas[0], separadorDaPrimeira);
  const linhasDeDados = mapaCabecalho ? linhas.slice(1) : linhas;

  return linhasDeDados
    .map((linha) => {
      const separador = linha.includes("\t") ? "\t" : linha.includes(";") ? ";" : ",";
      const campos = linha.split(separador).map((campo) => campo.trim());
      const valores: Partial<Record<CampoDestinatario, string>> = {};
      if (mapaCabecalho) {
        mapaCabecalho.forEach((campo, indice) => {
          if (campo && campos[indice]) valores[campo] = campos[indice];
        });
      } else {
        // Sem cabeçalho: nome, e-mail e, nas colunas seguintes, o que parece número é telefone e o resto é empresa.
        if (campos[0]) valores.nome = campos[0];
        if (campos[1]) valores.email = campos[1];
        for (const extra of campos.slice(2)) {
          if (!extra) continue;
          if (extra.replace(/\D/g, "").length >= 8 && !valores.telefone) valores.telefone = extra;
          else if (!valores.empresa) valores.empresa = extra;
        }
      }
      return {
        nome: valores.nome ?? "",
        email: valores.email || undefined,
        telefone: valores.telefone || undefined,
        empresa: valores.empresa || undefined,
      };
    })
    .filter((destinatario) => destinatario.nome && (destinatario.email || destinatario.telefone));
}

function toneStatusCampanha(status: string): "cyan" | "amber" | "green" | "muted" {
  if (status === "concluida") return "green";
  if (status === "enviando" || status === "pronta") return "amber";
  if (status === "rascunho") return "muted";
  return "cyan";
}

function toneStatusDestinatario(status: string): "cyan" | "green" | "red" | "muted" {
  if (status === "enviado") return "green";
  if (status === "falhou") return "red";
  if (status === "optout" || status === "retido" || status === "nao_enviado") return "muted";
  return "cyan";
}

// "retido" é o pendente que ficou fora de um envio só para selecionados; volta a pendente quando essa rodada termina.
function rotuloStatusDestinatario(status: string): string {
  if (status === "retido") return "fora desta rodada";
  if (status === "nao_enviado") return "não enviado";
  return status;
}

export function Campanhas() {
  const { usuario, marcarTutorialModuloVisto } = useAuth();
  // Tutorial do módulo (raio-X 2026-09-21) — abre sozinho na primeira
  // visita, coexiste com o tour grande.
  const [tutorialAberto, setTutorialAberto] = useState(false);
  const [carregado, setCarregado] = useState(false);
  useEffect(() => {
    if (usuario && carregado && !(usuario.tutoriais_modulo_vistos ?? []).includes("campanhas")) setTutorialAberto(true);
  }, [usuario, carregado]);
  function fecharTutorial() {
    setTutorialAberto(false);
    if (usuario && !(usuario.tutoriais_modulo_vistos ?? []).includes("campanhas")) marcarTutorialModuloVisto("campanhas");
  }
  const [campanhas, setCampanhas] = useState<Campanha[]>([]);
  const [campanhaSelecionadaId, setCampanhaSelecionadaId] = useState<number | null>(null);
  const [detalhe, setDetalhe] = useState<CampanhaDetalhe | null>(null);
  const [templates, setTemplates] = useState<TemplateWhatsApp[]>([]);
  const [canaisNovaCampanha, setCanaisNovaCampanha] = useState<Set<string>>(new Set(["email"]));

  const [icps, setIcps] = useState<ICP[]>([]);
  const [origemContas, setOrigemContas] = useState<"icp" | "leads">("icp");
  const [icpParaAudienciaId, setIcpParaAudienciaId] = useState<number | null>(null);
  const [contasParaAudiencia, setContasParaAudiencia] = useState<Conta[]>([]);
  const [contasSelecionadas, setContasSelecionadas] = useState<Set<number>>(new Set());
  const [abaDestinatarios, setAbaDestinatarios] = useState<"cadastrados" | "colar">("cadastrados");

  const [modalCriarAberto, setModalCriarAberto] = useState(false);
  const [adicionandoDestinatarios, setAdicionandoDestinatarios] = useState(false);
  const [confirmandoExclusao, setConfirmandoExclusao] = useState(false);
  const [confirmandoEdicao, setConfirmandoEdicao] = useState(false);
  const [modalEditarAberto, setModalEditarAberto] = useState(false);
  const [canaisEdicao, setCanaisEdicao] = useState<Set<string>>(new Set(["email"]));
  const [erro, setErro] = useState<string | null>(null);
  const [mensagem, setMensagem] = useState<string | null>(null);
  const [destinatariosMarcados, setDestinatariosMarcados] = useState<Set<number>>(new Set());
  const [previa, setPrevia] = useState<{ destinatario_nome: string | null; assunto: string; corpo: string } | null>(null);

  const campanhaSelecionada = campanhas.find((c) => c.id === campanhaSelecionadaId) ?? null;

  async function carregarCampanhas() {
    try {
      const resposta = await api.get<Campanha[]>("/campanhas");
      setCampanhas(resposta);
      if (resposta.length > 0 && campanhaSelecionadaId === null) {
        setCampanhaSelecionadaId(resposta[0].id);
      }
    } catch {
      setErro("Não foi possível carregar as campanhas.");
    } finally {
      setCarregado(true);
    }
  }

  async function carregarDetalhe(campanhaId: number) {
    try {
      setDetalhe(await api.get<CampanhaDetalhe>(`/campanhas/${campanhaId}`));
    } catch {
      setErro("Não foi possível carregar os detalhes da campanha.");
    }
  }

  useEffect(() => {
    carregarCampanhas();
    api
      .get<ICP[]>("/icp")
      .then(setIcps)
      .catch(() => undefined);
    api
      .get<TemplateWhatsApp[]>("/whatsapp/templates")
      .then((resposta) => setTemplates(resposta.filter((template) => template.status === "aprovado")))
      .catch(() => undefined);
  }, []);

  useEffect(() => {
    setDestinatariosMarcados(new Set());
    if (campanhaSelecionadaId !== null) carregarDetalhe(campanhaSelecionadaId);
    else setDetalhe(null);
  }, [campanhaSelecionadaId]);

  // Prévia do e-mail já personalizado ([Nome], [Empresa]) para o primeiro destinatário da lista; refaz quando o texto ou a lista muda.
  const textoDoEmail = campanhaSelecionada?.canais.includes("email") ? campanhaSelecionada.conteudo_email : null;
  useEffect(() => {
    setPrevia(null);
    if (campanhaSelecionadaId === null || !textoDoEmail) return;
    api
      .get<{ destinatario_nome: string | null; assunto: string; corpo: string }>(`/campanhas/${campanhaSelecionadaId}/previa`)
      .then(setPrevia)
      .catch(() => undefined);
  }, [campanhaSelecionadaId, textoDoEmail, campanhaSelecionada?.assunto, detalhe?.destinatarios.length]);

  // Enquanto a campanha está sendo enviada, o andamento (enviados/pendentes) se atualiza sozinho.
  const emEnvio = campanhaSelecionada?.status === "pronta" || campanhaSelecionada?.status === "enviando";

  // Quem ainda não recebeu pode ser marcado para um envio só a algumas pessoas (ex.: teste); quem já recebeu nunca recebe de novo.
  const idsElegiveis = (detalhe?.destinatarios ?? [])
    .filter((destinatario) => destinatario.status === "pendente" || destinatario.status === "falhou")
    .map((destinatario) => destinatario.id);
  const idsMarcados = idsElegiveis.filter((id) => destinatariosMarcados.has(id));
  useEffect(() => {
    if (!emEnvio || campanhaSelecionadaId === null) return;
    const id = window.setInterval(() => {
      carregarCampanhas();
      carregarDetalhe(campanhaSelecionadaId);
    }, 5000);
    return () => window.clearInterval(id);
  }, [emEnvio, campanhaSelecionadaId]);

  useEffect(() => {
    setContasSelecionadas(new Set());
    if (origemContas === "leads") {
      api
        .get<Conta[]>("/leads/contas")
        .then(setContasParaAudiencia)
        .catch(() => setErro("Não foi possível carregar os clientes cadastrados."));
      return;
    }
    if (icpParaAudienciaId === null) {
      setContasParaAudiencia([]);
      return;
    }
    api
      .get<Conta[]>(`/icp/${icpParaAudienciaId}/contas`)
      .then(setContasParaAudiencia)
      .catch(() => setErro("Não foi possível carregar as contas do ICP."));
  }, [origemContas, icpParaAudienciaId]);

  function alternarConta(contaId: number) {
    setContasSelecionadas((atual) => {
      const nova = new Set(atual);
      if (nova.has(contaId)) nova.delete(contaId);
      else nova.add(contaId);
      return nova;
    });
  }

  function alternarCanalNovaCampanha(canal: string) {
    setCanaisNovaCampanha((atual) => {
      const nova = new Set(atual);
      if (nova.has(canal)) nova.delete(canal);
      else nova.add(canal);
      return nova;
    });
  }

  async function criarCampanha(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const canais = Array.from(canaisNovaCampanha);
    if (canais.length === 0) {
      setErro("Selecione ao menos um canal.");
      return;
    }
    try {
      const criada = await api.post<Campanha>("/campanhas", {
        nome: String(form.get("nome")),
        tipo: String(form.get("tipo")),
        canais,
        assunto: canais.includes("email") ? String(form.get("assunto") || "") || null : null,
        conteudo_email: canais.includes("email") ? String(form.get("conteudo_email") || "") || null : null,
        template_whatsapp_id: canais.includes("whatsapp") ? String(form.get("template_whatsapp_id") || "") || null : null,
      });
      setModalCriarAberto(false);
      setCanaisNovaCampanha(new Set(["email"]));
      await carregarCampanhas();
      setCampanhaSelecionadaId(criada.id);
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível criar a campanha.");
    }
  }

  async function adicionarContatosCadastrados() {
    if (campanhaSelecionadaId === null || contasSelecionadas.size === 0) return;
    setAdicionandoDestinatarios(true);
    setErro(null);
    try {
      const decisoresPorConta = await Promise.all(
        Array.from(contasSelecionadas).map((contaId) => api.get<Decisor[]>(`/contas/${contaId}/decisores`)),
      );
      const decisorIds = Array.from(new Set(decisoresPorConta.flat().map((decisor) => decisor.id)));
      if (decisorIds.length === 0) {
        setErro("Nenhuma das contas selecionadas tem contato cadastrado.");
        return;
      }
      await api.post(`/campanhas/${campanhaSelecionadaId}/destinatarios/decisores`, { decisor_ids: decisorIds });
      setContasSelecionadas(new Set());
      await carregarDetalhe(campanhaSelecionadaId);
      setMensagem(`${decisorIds.length} contato(s) adicionado(s).`);
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível adicionar os contatos.");
    } finally {
      setAdicionandoDestinatarios(false);
    }
  }

  async function adicionarListaColada(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (campanhaSelecionadaId === null) return;
    const form = new FormData(event.currentTarget);
    const destinatarios = parseDestinatarios(String(form.get("lista") ?? ""));
    if (destinatarios.length === 0) {
      setErro("Cole ao menos uma linha válida (Nome e e-mail ou telefone são obrigatórios).");
      return;
    }
    const formulario = event.currentTarget;
    setAdicionandoDestinatarios(true);
    setErro(null);
    try {
      const adicionados = await api.post<unknown[]>(`/campanhas/${campanhaSelecionadaId}/destinatarios/avulsos`, { destinatarios });
      formulario.reset();
      await carregarDetalhe(campanhaSelecionadaId);
      const ignorados = destinatarios.length - adicionados.length;
      setMensagem(
        `${adicionados.length} destinatário(s) adicionado(s)` +
          (ignorados > 0 ? `; ${ignorados} ignorado(s) por não ter e-mail válido nem telefone, ou já estar na lista.` : "."),
      );
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível adicionar a lista.");
    } finally {
      setAdicionandoDestinatarios(false);
    }
  }

  async function removerDestinatario(destinatarioId: number) {
    if (campanhaSelecionadaId === null) return;
    try {
      await api.delete(`/campanhas/${campanhaSelecionadaId}/destinatarios/${destinatarioId}`);
      await carregarDetalhe(campanhaSelecionadaId);
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível remover o destinatário.");
    }
  }

  function alternarDestinatario(destinatarioId: number) {
    setDestinatariosMarcados((atual) => {
      const nova = new Set(atual);
      if (nova.has(destinatarioId)) nova.delete(destinatarioId);
      else nova.add(destinatarioId);
      return nova;
    });
  }

  function alternarTodosOsElegiveis() {
    setDestinatariosMarcados(idsMarcados.length === idsElegiveis.length ? new Set() : new Set(idsElegiveis));
  }

  // Sem `ids` envia a todos os pendentes; com `ids`, só a esses (os demais continuam pendentes para o próximo envio).
  async function marcarPronta(ids?: number[]) {
    if (campanhaSelecionadaId === null) return;
    setErro(null);
    try {
      await api.post(`/campanhas/${campanhaSelecionadaId}/marcar-pronta`, ids ? { destinatario_ids: ids } : undefined);
      setDestinatariosMarcados(new Set());
      setMensagem(
        ids
          ? `Envio iniciado para ${ids.length} destinatário(s) selecionado(s). Os demais continuam pendentes e a campanha volta para rascunho quando terminar.`
          : "Campanha marcada como pronta — o envio começou agora. Acompanhe o andamento abaixo; se algo interromper, o ciclo automático continua de onde parou.",
      );
      await carregarCampanhas();
      await carregarDetalhe(campanhaSelecionadaId);
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível marcar a campanha como pronta.");
    }
  }

  function abrirEdicao() {
    if (!campanhaSelecionada) return;
    setCanaisEdicao(new Set(campanhaSelecionada.canais));
    setConfirmandoEdicao(false);
    setModalEditarAberto(true);
  }

  // Campanha já pronta/enviando/concluída só pode ser editada como rascunho: quem já recebeu não recebe de novo e quem falhou volta para a fila.
  async function voltarParaRascunhoEEditar() {
    if (campanhaSelecionadaId === null) return;
    setErro(null);
    try {
      await api.post(`/campanhas/${campanhaSelecionadaId}/voltar-para-rascunho`);
      await carregarCampanhas();
      await carregarDetalhe(campanhaSelecionadaId);
      abrirEdicao();
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível voltar a campanha para rascunho.");
    }
  }

  function alternarCanalEdicao(canal: string) {
    setCanaisEdicao((atual) => {
      const nova = new Set(atual);
      if (nova.has(canal)) nova.delete(canal);
      else nova.add(canal);
      return nova;
    });
  }

  async function salvarEdicao(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (campanhaSelecionadaId === null) return;
    const form = new FormData(event.currentTarget);
    const canais = Array.from(canaisEdicao);
    if (canais.length === 0) {
      setErro("Selecione ao menos um canal.");
      return;
    }
    setErro(null);
    try {
      await api.put(`/campanhas/${campanhaSelecionadaId}`, {
        nome: String(form.get("nome")),
        tipo: String(form.get("tipo")),
        canais,
        assunto: canais.includes("email") ? String(form.get("assunto") || "") || null : null,
        conteudo_email: canais.includes("email") ? String(form.get("conteudo_email") || "") || null : null,
        template_whatsapp_id: canais.includes("whatsapp") ? String(form.get("template_whatsapp_id") || "") || null : null,
      });
      setModalEditarAberto(false);
      setMensagem("Campanha atualizada. Revise e clique em “Marcar como pronta” para enviar.");
      await carregarCampanhas();
      await carregarDetalhe(campanhaSelecionadaId);
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível salvar a campanha.");
    }
  }

  async function excluirCampanha() {
    if (campanhaSelecionadaId === null) return;
    setErro(null);
    try {
      await api.delete(`/campanhas/${campanhaSelecionadaId}`);
      setConfirmandoExclusao(false);
      setCampanhaSelecionadaId(null);
      setMensagem("Campanha excluída.");
      await carregarCampanhas();
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível excluir a campanha.");
    }
  }

  return (
    <div className="p-5.5">
      <div className="mb-5 flex items-end justify-between">
        <div>
          <div className="flex items-center gap-2">
            <div className="font-head text-xl font-bold">Campanhas</div>
            <button type="button" onClick={() => setTutorialAberto(true)} className="text-[11px] text-muted hover:text-cyan">
              🔄 Rever tutorial
            </button>
          </div>
          <div className="mt-0.5 text-[11px] text-muted">
            Disparo de e-mail/WhatsApp em massa — sem personalização por IA, separado da Cadência
          </div>
        </div>
        <Button size="sm" variant="violet" data-tutorial-id="campanhas:nova" onClick={() => setModalCriarAberto(true)}>
          + Nova campanha
        </Button>
      </div>

      {erro && <div className="mb-4 text-[12px] text-red">{erro}</div>}
      {mensagem && <div className="mb-4 text-[12px] text-green">{mensagem}</div>}

      <Card className="mb-4">
        <SectionLabel>Campanhas</SectionLabel>
        <div className="flex flex-wrap gap-2">
          {campanhas.map((campanha) => (
            <button
              key={campanha.id}
              onClick={() => {
                setCampanhaSelecionadaId(campanha.id);
                setConfirmandoExclusao(false);
              }}
              className={`rounded-lg border px-3 py-1.5 text-[12px] ${
                campanha.id === campanhaSelecionadaId
                  ? "border-cyan bg-cyan/15 text-cyan"
                  : "border-border text-muted hover:text-text"
              }`}
            >
              {campanha.nome} <Badge tone={toneStatusCampanha(campanha.status)}>{campanha.status}</Badge>
            </button>
          ))}
          {campanhas.length === 0 && <div className="text-[12px] text-muted">Nenhuma campanha criada ainda.</div>}
        </div>
      </Card>

      {campanhaSelecionada && detalhe && (
        <>
          <Card className="mb-4">
            <div className="mb-2 flex items-center justify-between">
              <SectionLabel>{campanhaSelecionada.nome}</SectionLabel>
              <div className="flex items-center gap-2">
                <Badge tone={toneStatusCampanha(campanhaSelecionada.status)}>{campanhaSelecionada.status}</Badge>
                {!confirmandoExclusao && !confirmandoEdicao && (
                  <Button
                    size="sm"
                    variant="ghost"
                    data-tutorial-id="campanhas:editar"
                    onClick={() => (campanhaSelecionada.status === "rascunho" ? abrirEdicao() : setConfirmandoEdicao(true))}
                  >
                    Editar e-mail e dados
                  </Button>
                )}
                {confirmandoEdicao && (
                  <>
                    <span className="max-w-[320px] text-[11px] text-muted">
                      Para editar, a campanha volta para rascunho. Quem já recebeu não recebe de novo; os que falharam voltam para a fila.
                    </span>
                    <Button size="sm" onClick={voltarParaRascunhoEEditar}>
                      Continuar
                    </Button>
                    <Button size="sm" variant="ghost" onClick={() => setConfirmandoEdicao(false)}>
                      Cancelar
                    </Button>
                  </>
                )}
                {campanhaSelecionada.status === "rascunho" && !confirmandoExclusao && (
                  <>
                    {idsMarcados.length > 0 && (
                      <Button size="sm" onClick={() => marcarPronta(idsMarcados)}>
                        Enviar só para os selecionados ({idsMarcados.length})
                      </Button>
                    )}
                    <Button
                      size="sm"
                      variant={idsMarcados.length > 0 ? "ghost" : "primary"}
                      data-tutorial-id="campanhas:pronta"
                      onClick={() => marcarPronta()}
                    >
                      Marcar como pronta
                    </Button>
                    <Button size="sm" variant="danger" onClick={() => setConfirmandoExclusao(true)}>
                      Excluir
                    </Button>
                  </>
                )}
                {confirmandoExclusao && (
                  <>
                    <span className="text-[11px] text-muted">Excluir esta campanha?</span>
                    <Button size="sm" variant="danger" onClick={excluirCampanha}>
                      Confirmar
                    </Button>
                    <Button size="sm" variant="ghost" onClick={() => setConfirmandoExclusao(false)}>
                      Cancelar
                    </Button>
                  </>
                )}
              </div>
            </div>
            <div className="flex flex-wrap items-center gap-1.5 text-[11px] text-muted">
              <Badge tone="cyan">{campanhaSelecionada.tipo}</Badge>
              {campanhaSelecionada.canais.map((canal) => (
                <Badge key={canal} tone="cyan">
                  {canal}
                </Badge>
              ))}
              {campanhaSelecionada.assunto && <span>· Assunto: {campanhaSelecionada.assunto}</span>}
              {campanhaSelecionada.template_whatsapp_id && <span>· Template: {campanhaSelecionada.template_whatsapp_id}</span>}
            </div>
            {campanhaSelecionada.canais.includes("email") && campanhaSelecionada.conteudo_email && (
              <details className="mt-2 rounded-lg border border-border p-2 text-[12px]">
                <summary className="cursor-pointer text-muted">Ver o texto do e-mail</summary>
                <div className="mt-2 font-semibold">{campanhaSelecionada.assunto}</div>
                <div className="mt-1 whitespace-pre-wrap text-muted">{campanhaSelecionada.conteudo_email}</div>
                {previa && (
                  <div className="mt-3 rounded-md bg-surf2 p-2">
                    <div className="mb-1 text-[10px] tracking-wide text-muted uppercase">
                      {previa.destinatario_nome ? `Como chega para ${previa.destinatario_nome}` : "Como chega (sem destinatário ainda)"}
                    </div>
                    <div className="font-semibold">{previa.assunto}</div>
                    <div className="mt-1 whitespace-pre-wrap">{previa.corpo}</div>
                  </div>
                )}
              </details>
            )}

            <div className="mt-3 grid grid-cols-4 gap-2">
              {Object.entries(detalhe.metricas).map(([chave, valor]) => (
                <div key={chave} className="rounded-lg border border-border p-2 text-center">
                  <div className="text-[9.5px] tracking-wide text-muted uppercase">{rotuloStatusDestinatario(chave).replace("fora desta rodada", "fora da rodada")}</div>
                  <div className="font-head text-lg font-bold">{valor}</div>
                </div>
              ))}
            </div>
          </Card>

          {campanhaSelecionada.status === "rascunho" && (
            <Card className="mb-4">
              <SectionLabel>Adicionar destinatários</SectionLabel>
              <div className="mb-3 flex gap-2">
                <button
                  type="button"
                  onClick={() => setAbaDestinatarios("cadastrados")}
                  className={`rounded-lg border px-3 py-1.5 text-[12px] ${
                    abaDestinatarios === "cadastrados" ? "border-cyan bg-cyan/15 text-cyan" : "border-border text-muted"
                  }`}
                >
                  Contatos cadastrados
                </button>
                <button
                  type="button"
                  onClick={() => setAbaDestinatarios("colar")}
                  className={`rounded-lg border px-3 py-1.5 text-[12px] ${
                    abaDestinatarios === "colar" ? "border-cyan bg-cyan/15 text-cyan" : "border-border text-muted"
                  }`}
                >
                  Colar lista
                </button>
              </div>

              {abaDestinatarios === "cadastrados" ? (
                <div>
                  <div className="mb-2 flex gap-2">
                    <button
                      type="button"
                      onClick={() => setOrigemContas("icp")}
                      className={`rounded-lg border px-3 py-1.5 text-[12px] ${
                        origemContas === "icp" ? "border-cyan bg-cyan/15 text-cyan" : "border-border text-muted"
                      }`}
                    >
                      Por ICP
                    </button>
                    <button
                      type="button"
                      onClick={() => setOrigemContas("leads")}
                      className={`rounded-lg border px-3 py-1.5 text-[12px] ${
                        origemContas === "leads" ? "border-cyan bg-cyan/15 text-cyan" : "border-border text-muted"
                      }`}
                    >
                      Clientes Cadastrados
                    </button>
                  </div>

                  {origemContas === "icp" && (
                    <div className="mb-3">
                      <Select
                        value={icpParaAudienciaId ?? ""}
                        onChange={(event) => setIcpParaAudienciaId(event.target.value ? Number(event.target.value) : null)}
                      >
                        <option value="">Selecione um ICP</option>
                        {icps.map((icp) => (
                          <option key={icp.id} value={icp.id}>
                            {icp.nome}
                          </option>
                        ))}
                      </Select>
                    </div>
                  )}

                  {contasParaAudiencia.length > 0 && (
                    <div className="mb-3 flex max-h-64 flex-col gap-1 overflow-y-auto rounded-lg border border-border p-2">
                      {contasParaAudiencia.map((conta) => (
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
                  )}
                  {contasParaAudiencia.length === 0 && (
                    <div className="mb-3 text-[12px] text-muted">
                      {origemContas === "leads" ? "Nenhum cliente cadastrado ainda." : "Selecione um ICP com contas geradas."}
                    </div>
                  )}

                  <Button
                    disabled={contasSelecionadas.size === 0 || adicionandoDestinatarios}
                    onClick={adicionarContatosCadastrados}
                  >
                    {adicionandoDestinatarios
                      ? "Adicionando..."
                      : `Adicionar contatos de ${contasSelecionadas.size} conta(s)`}
                  </Button>
                  <div className="mt-1.5 text-[11px] text-muted">
                    Adiciona todos os contatos já cadastrados nas contas marcadas.
                  </div>
                </div>
              ) : (
                <form onSubmit={adicionarListaColada} className="flex flex-col gap-2">
                  <Textarea
                    name="lista"
                    rows={6}
                    placeholder={"Nome, E-mail, Telefone, Empresa\nFulano de Tal, fulano@empresa.com, 11999999999, Acme Ltda"}
                  />
                  <div className="text-[10px] text-muted">
                    Colunas: Nome, E-mail, Telefone e Empresa (a empresa é opcional e alimenta o [Empresa] do e-mail). Sem cabeçalho, o que não for número de
                    telefone vira empresa; com cabeçalho, use os nomes das colunas.
                  </div>
                  <Button type="submit" disabled={adicionandoDestinatarios}>
                    {adicionandoDestinatarios ? "Adicionando..." : "Adicionar lista"}
                  </Button>
                </form>
              )}
            </Card>
          )}

          <Card data-tutorial-id="campanhas:destinatarios">
            <SectionLabel>Destinatários ({detalhe.destinatarios.length})</SectionLabel>
            {campanhaSelecionada.status === "rascunho" && idsElegiveis.length > 0 && (
              <div className="mb-2 text-[11px] text-muted">
                Marque as caixas para enviar só a algumas pessoas (por exemplo, um teste). “Marcar como pronta” envia a todos os que ainda não
                receberam; quem já recebeu nunca recebe de novo.
              </div>
            )}
            <table className="w-full border-collapse text-[12px]">
              <thead>
                <tr className="border-b border-border text-[9.5px] tracking-wide text-muted uppercase">
                  {campanhaSelecionada.status === "rascunho" && (
                    <th className="w-8 p-2 text-left">
                      <input
                        type="checkbox"
                        aria-label="Selecionar todos os que ainda não receberam"
                        disabled={idsElegiveis.length === 0}
                        checked={idsElegiveis.length > 0 && idsMarcados.length === idsElegiveis.length}
                        onChange={alternarTodosOsElegiveis}
                      />
                    </th>
                  )}
                  <th className="p-2 text-left">Nome</th>
                  <th className="p-2 text-left">E-mail</th>
                  <th className="p-2 text-left">Telefone</th>
                  <th className="p-2 text-left">Empresa</th>
                  <th className="p-2 text-left">Status</th>
                  {campanhaSelecionada.status === "rascunho" && <th className="p-2 text-left">Ações</th>}
                </tr>
              </thead>
              <tbody>
                {detalhe.destinatarios.map((destinatario) => (
                  <tr key={destinatario.id} className="border-b border-border">
                    {campanhaSelecionada.status === "rascunho" && (
                      <td className="p-2">
                        <input
                          type="checkbox"
                          aria-label={`Enviar para ${destinatario.nome}`}
                          disabled={!idsElegiveis.includes(destinatario.id)}
                          checked={destinatariosMarcados.has(destinatario.id)}
                          onChange={() => alternarDestinatario(destinatario.id)}
                        />
                      </td>
                    )}
                    <td className="p-2 font-semibold">{destinatario.nome}</td>
                    <td className="p-2 text-muted">{destinatario.email ?? "—"}</td>
                    <td className="p-2 text-muted">{destinatario.telefone ?? "—"}</td>
                    <td className="p-2 text-muted">{destinatario.empresa ?? "—"}</td>
                    <td className="p-2">
                      <Badge tone={toneStatusDestinatario(destinatario.status)}>{rotuloStatusDestinatario(destinatario.status)}</Badge>
                      {destinatario.motivo_falha && (
                        <div className={`mt-0.5 text-[10px] ${destinatario.status === "nao_enviado" ? "text-muted" : "text-red"}`}>{destinatario.motivo_falha}</div>
                      )}
                    </td>
                    {campanhaSelecionada.status === "rascunho" && (
                      <td className="p-2">
                        <Button size="sm" variant="ghost" onClick={() => removerDestinatario(destinatario.id)}>
                          Remover
                        </Button>
                      </td>
                    )}
                  </tr>
                ))}
                {detalhe.destinatarios.length === 0 && (
                  <tr>
                    <td colSpan={7} className="p-4 text-center text-muted">
                      Nenhum destinatário adicionado ainda.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </Card>
        </>
      )}

      <Modal title="Nova campanha" open={modalCriarAberto} onClose={() => setModalCriarAberto(false)}>
        <form onSubmit={criarCampanha} className="flex flex-col gap-3">
          <div>
            <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">Nome</div>
            <Input name="nome" required placeholder="Ex.: Black Friday 2026" />
          </div>
          <div>
            <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">Tipo</div>
            <Select name="tipo" defaultValue="marketing">
              <option value="marketing">Marketing</option>
              <option value="vendas">Vendas</option>
            </Select>
          </div>

          <div>
            <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">Canais</div>
            <div className="flex gap-3">
              <label className="flex items-center gap-1.5 text-[12px]">
                <input
                  type="checkbox"
                  checked={canaisNovaCampanha.has("email")}
                  onChange={() => alternarCanalNovaCampanha("email")}
                />
                E-mail
              </label>
              <label className="flex items-center gap-1.5 text-[12px]">
                <input
                  type="checkbox"
                  checked={canaisNovaCampanha.has("whatsapp")}
                  onChange={() => alternarCanalNovaCampanha("whatsapp")}
                />
                WhatsApp
              </label>
            </div>
          </div>

          {canaisNovaCampanha.has("email") && (
            <>
              <div>
                <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">Assunto do e-mail</div>
                <Input name="assunto" required placeholder="Ex.: Condições especiais só até domingo" />
              </div>
              <div>
                <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">Conteúdo do e-mail</div>
                <Textarea name="conteudo_email" required rows={5} placeholder="Corpo do e-mail em texto simples." />
                <div className="mt-1 text-[10px] text-muted">Personalize com [Nome] (primeiro nome), [Nome completo] e [Empresa]. Sem o nome fica só “Olá!”; sem a empresa entra “a sua empresa”.</div>
              </div>
            </>
          )}

          {canaisNovaCampanha.has("whatsapp") && (
            <div>
              <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">Template do WhatsApp (aprovado)</div>
              <Select name="template_whatsapp_id" required defaultValue="">
                <option value="" disabled>
                  Selecione um template
                </option>
                {templates.map((template) => (
                  <option key={template.id} value={template.nome}>
                    {template.nome}
                  </option>
                ))}
              </Select>
              {templates.length === 0 && (
                <div className="mt-1 text-[11px] text-amber">
                  Nenhum template aprovado encontrado — cadastre e aguarde aprovação da Meta antes de disparar por
                  WhatsApp.
                </div>
              )}
            </div>
          )}

          <Button type="submit" className="mt-1 w-full justify-center">
            Criar campanha
          </Button>
        </form>
      </Modal>

      <Modal title="Editar campanha" open={modalEditarAberto} onClose={() => setModalEditarAberto(false)}>
        {campanhaSelecionada && (
          <form key={campanhaSelecionada.id} onSubmit={salvarEdicao} className="flex flex-col gap-3">
            <div>
              <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">Nome</div>
              <Input name="nome" required defaultValue={campanhaSelecionada.nome} />
            </div>
            <div>
              <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">Tipo</div>
              <Select name="tipo" defaultValue={campanhaSelecionada.tipo}>
                <option value="marketing">Marketing</option>
                <option value="vendas">Vendas</option>
              </Select>
            </div>
            <div>
              <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">Canais</div>
              <div className="flex gap-3">
                <label className="flex items-center gap-1.5 text-[12px]">
                  <input type="checkbox" checked={canaisEdicao.has("email")} onChange={() => alternarCanalEdicao("email")} />
                  E-mail
                </label>
                <label className="flex items-center gap-1.5 text-[12px]">
                  <input type="checkbox" checked={canaisEdicao.has("whatsapp")} onChange={() => alternarCanalEdicao("whatsapp")} />
                  WhatsApp
                </label>
              </div>
            </div>
            {canaisEdicao.has("email") && (
              <>
                <div>
                  <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">Assunto do e-mail</div>
                  <Input name="assunto" required defaultValue={campanhaSelecionada.assunto ?? ""} />
                </div>
                <div>
                  <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">Conteúdo do e-mail</div>
                  <Textarea name="conteudo_email" required rows={8} defaultValue={campanhaSelecionada.conteudo_email ?? ""} />
                  <div className="mt-1 text-[10px] text-muted">Personalize com [Nome] (primeiro nome), [Nome completo] e [Empresa]. Sem o nome fica só “Olá!”; sem a empresa entra “a sua empresa”.</div>
                </div>
              </>
            )}
            {canaisEdicao.has("whatsapp") && (
              <div>
                <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">Template do WhatsApp (aprovado)</div>
                <Select name="template_whatsapp_id" required defaultValue={campanhaSelecionada.template_whatsapp_id ?? ""}>
                  <option value="" disabled>
                    Selecione um template
                  </option>
                  {templates.map((template) => (
                    <option key={template.id} value={template.nome}>
                      {template.nome}
                    </option>
                  ))}
                </Select>
              </div>
            )}
            <Button type="submit" className="mt-1 w-full justify-center">
              Salvar alterações
            </Button>
          </form>
        )}
      </Modal>

      <TutorialCampanhas open={tutorialAberto} onClose={fecharTutorial} />
    </div>
  );
}
