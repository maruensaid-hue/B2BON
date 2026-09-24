import { useEffect, useState } from "react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Select, Textarea } from "@/components/ui/Input";
import { TutorialAprovacoes } from "@/pages/aprovacoes/TutorialAprovacoes";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";

interface ItemFila {
  aprovacao_id: number;
  status: string;
  mensagem_id: number;
  canal: string;
  template_id: string | null;
  assunto: string | null;
  conteudo: string;
  cadencia_id: number | null;
  conta_id: number;
  decisor_id: number;
  decisor_nome: string;
  decisor_email: string | null;
  criado_em: string;
}

function toneCanal(canal: string): "cyan" | "green" | "violet" {
  if (canal === "whatsapp") return "green";
  if (canal === "linkedin") return "violet";
  return "cyan";
}

function toneStatus(status: string): "green" | "muted" | "amber" {
  if (status === "aprovado") return "green";
  if (status === "rejeitado") return "muted";
  return "amber";
}

// Raio-X 2026-09-01: uma mensagem rejeitada ficava invisível pra sempre
// (a tela só mostrava "pendente"), mas continuava bloqueando a ativação
// da cadência dela pra sempre (`cadencia_service.ativar` exige status
// "aprovado" em toda mensagem) — sem jeito nenhum de achar ou corrigir
// pela tela. Filtro de status deixa ver rejeitadas/aprovadas também.
const OPCOES_STATUS = [
  { valor: "pendente", rotulo: "Pendentes" },
  { valor: "rejeitado", rotulo: "Rejeitadas" },
  { valor: "aprovado", rotulo: "Aprovadas" },
  { valor: "", rotulo: "Todas" },
];

export function Aprovacoes() {
  const { usuario, marcarTutorialModuloVisto } = useAuth();
  // Tutorial do módulo (raio-X 2026-09-21) — abre sozinho na primeira
  // visita, coexiste com o tour grande.
  const [tutorialAberto, setTutorialAberto] = useState(false);
  const [carregado, setCarregado] = useState(false);
  useEffect(() => {
    if (usuario && carregado && !(usuario.tutoriais_modulo_vistos ?? []).includes("aprovacoes")) setTutorialAberto(true);
  }, [usuario, carregado]);
  function fecharTutorial() {
    setTutorialAberto(false);
    if (usuario && !(usuario.tutoriais_modulo_vistos ?? []).includes("aprovacoes")) marcarTutorialModuloVisto("aprovacoes");
  }
  const [itens, setItens] = useState<ItemFila[]>([]);
  const [filtroCanal, setFiltroCanal] = useState("");
  const [filtroStatus, setFiltroStatus] = useState("pendente");
  const [textoEditado, setTextoEditado] = useState<Record<number, string>>({});
  // E-mail aparece colapsado no formato padrão de cliente de e-mail
  // (raio-X 2026-09-24) — mesmo padrão de disclosure de
  // `ContaDetalheModal.tsx` (decisorExpandidoId), sem fetch nenhum aqui
  // porque o conteúdo já vem carregado na própria listagem.
  const [itemExpandidoId, setItemExpandidoId] = useState<number | null>(null);
  function alternarExpansaoItem(aprovacaoId: number) {
    setItemExpandidoId((atual) => (atual === aprovacaoId ? null : aprovacaoId));
  }
  const [erro, setErro] = useState<string | null>(null);
  const [mensagem, setMensagem] = useState<string | null>(null);

  async function carregar() {
    try {
      const params = new URLSearchParams();
      if (filtroStatus) params.set("status", filtroStatus);
      if (filtroCanal) params.set("canal", filtroCanal);
      const resposta = await api.get<ItemFila[]>(`/aprovacoes?${params.toString()}`);
      setItens(resposta);
    } catch {
      setErro("Não foi possível carregar a fila de aprovação.");
    } finally {
      setCarregado(true);
    }
  }

  useEffect(() => {
    carregar();
  }, [filtroCanal, filtroStatus]);

  async function aprovar(aprovacaoId: number) {
    try {
      await api.post(`/aprovacoes/${aprovacaoId}/aprovar`);
      setMensagem("Mensagem aprovada.");
      await carregar();
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível aprovar.");
    }
  }

  async function rejeitar(aprovacaoId: number) {
    try {
      await api.post(`/aprovacoes/${aprovacaoId}/rejeitar`, {});
      setMensagem("Mensagem rejeitada.");
      await carregar();
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível rejeitar.");
    }
  }

  async function salvarEdicao(item: ItemFila) {
    const novoConteudo = textoEditado[item.aprovacao_id];
    if (novoConteudo === undefined || novoConteudo === item.conteudo) return;
    try {
      await api.put(`/aprovacoes/${item.aprovacao_id}/mensagem`, { conteudo: novoConteudo });
      setMensagem("Mensagem editada.");
      await carregar();
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível salvar a edição.");
    }
  }

  async function aprovarTudoVisivel() {
    if (itens.length === 0) return;
    try {
      await api.post("/aprovacoes/aprovar-lote", { ids: itens.map((item) => item.aprovacao_id) });
      setMensagem(`${itens.length} mensagem(ns) aprovadas.`);
      await carregar();
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível aprovar em lote.");
    }
  }

  async function excluir(aprovacaoId: number) {
    if (!window.confirm("Excluir esta mensagem definitivamente? Essa ação não pode ser desfeita.")) return;
    try {
      await api.delete(`/aprovacoes/${aprovacaoId}`);
      setMensagem("Mensagem excluída.");
      await carregar();
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível excluir.");
    }
  }

  async function excluirTudoVisivel() {
    if (itens.length === 0) return;
    if (
      !window.confirm(
        `Excluir definitivamente ${itens.length} mensagem(ns) visíveis com este filtro? Essa ação não pode ser desfeita.`,
      )
    )
      return;
    try {
      const resultado = await api.post<{ excluidas: number }>("/aprovacoes/excluir-lote", {
        ids: itens.map((item) => item.aprovacao_id),
      });
      setMensagem(`${resultado.excluidas} mensagem(ns) excluída(s).`);
      await carregar();
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível excluir em lote.");
    }
  }

  return (
    <div className="p-5.5">
      <div className="mb-5 flex items-end justify-between">
        <div>
          <div className="flex items-center gap-2">
            <div className="font-head text-xl font-bold">Fila de Aprovação</div>
            <button type="button" onClick={() => setTutorialAberto(true)} className="text-[11px] text-muted hover:text-cyan">
              🔄 Rever tutorial
            </button>
          </div>
          <div className="mt-0.5 text-[11px] text-muted">
            Mensagens geradas por IA aguardando revisão antes de entrar na fila de envio
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Select data-tutorial-id="aprovacoes:filtro-status" value={filtroStatus} onChange={(event) => setFiltroStatus(event.target.value)} className="w-36">
            {OPCOES_STATUS.map((opcao) => (
              <option key={opcao.valor} value={opcao.valor}>
                {opcao.rotulo}
              </option>
            ))}
          </Select>
          <Select value={filtroCanal} onChange={(event) => setFiltroCanal(event.target.value)} className="w-36">
            <option value="">Todos os canais</option>
            <option value="email">E-mail</option>
            <option value="whatsapp">WhatsApp</option>
            <option value="linkedin">LinkedIn</option>
          </Select>
          {filtroStatus === "pendente" && (
            <Button size="sm" variant="violet" data-tutorial-id="aprovacoes:aprovar-todas" disabled={itens.length === 0} onClick={aprovarTudoVisivel}>
              Aprovar todas ({itens.length})
            </Button>
          )}
          {filtroStatus !== "" && (
            <Button size="sm" variant="danger" disabled={itens.length === 0} onClick={excluirTudoVisivel}>
              Excluir todas ({itens.length})
            </Button>
          )}
        </div>
      </div>

      {erro && <div className="mb-4 text-[12px] text-red">{erro}</div>}
      {mensagem && <div className="mb-4 text-[12px] text-green">{mensagem}</div>}

      <div className="flex flex-col gap-3">
        {itens.map((item) => {
          // "pendente"/"editado" permitem editar e rejeitar normalmente.
          // "rejeitado" só oferece "Aprovar mesmo assim" — o único jeito de
          // destravar uma cadência presa por uma rejeição antiga, já que o
          // backend não bloqueia aprovar por cima de um status anterior.
          const editavel = item.status === "pendente" || item.status === "editado";
          const isEmail = item.canal === "email";
          const expandido = itemExpandidoId === item.aprovacao_id;
          return (
            <Card key={item.aprovacao_id}>
              <div className="mb-2 flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Badge tone={toneCanal(item.canal)}>{item.canal}</Badge>
                  {item.status !== "pendente" && <Badge tone={toneStatus(item.status)}>{item.status}</Badge>}
                  {!isEmail && <span className="text-[11px] text-muted">conta #{item.conta_id} · {item.decisor_nome}</span>}
                </div>
                <span className="text-[10px] text-muted">{new Date(item.criado_em).toLocaleString("pt-BR")}</span>
              </div>
              {isEmail ? (
                <button
                  type="button"
                  onClick={() => alternarExpansaoItem(item.aprovacao_id)}
                  className="mb-2 flex w-full items-center gap-1.5 rounded-md bg-surf2 p-2 text-left text-[11px] text-text hover:border-cyan/50"
                >
                  <span className="text-muted">{expandido ? "▾" : "▸"}</span>
                  <span className="truncate">
                    Para: <span className="font-semibold">{item.decisor_nome}</span>{" "}
                    <span className="text-muted">&lt;{item.decisor_email ?? "sem e-mail"}&gt;</span>
                    {" · "}
                    {new Date(item.criado_em).toLocaleDateString("pt-BR")}
                    {" · "}
                    <span className="font-semibold">{item.assunto ?? "(sem assunto)"}</span>
                  </span>
                </button>
              ) : null}
              {(!isEmail || expandido) && (
                <Textarea
                  rows={4}
                  readOnly={!editavel}
                  defaultValue={item.conteudo}
                  onChange={(event) =>
                    setTextoEditado((atual) => ({ ...atual, [item.aprovacao_id]: event.target.value }))
                  }
                />
              )}
              <div className="mt-2 flex justify-end gap-2">
                {editavel &&
                  textoEditado[item.aprovacao_id] !== undefined &&
                  textoEditado[item.aprovacao_id] !== item.conteudo && (
                    <Button size="sm" onClick={() => salvarEdicao(item)}>
                      Salvar edição
                    </Button>
                  )}
                {editavel && (
                  <Button size="sm" variant="danger" onClick={() => rejeitar(item.aprovacao_id)}>
                    Rejeitar
                  </Button>
                )}
                {item.status !== "aprovado" && (
                  <Button size="sm" variant="green" data-tutorial-id="aprovacoes:aprovar-item" onClick={() => aprovar(item.aprovacao_id)}>
                    {item.status === "rejeitado" ? "Aprovar mesmo assim" : "Aprovar"}
                  </Button>
                )}
                <Button size="sm" variant="danger" onClick={() => excluir(item.aprovacao_id)}>
                  Excluir
                </Button>
              </div>
            </Card>
          );
        })}
        {itens.length === 0 && (
          <Card>
            <div className="text-center text-[12px] text-muted">
              {filtroStatus === "pendente"
                ? "Nenhuma mensagem pendente de aprovação."
                : "Nenhuma mensagem encontrada com esse filtro."}
            </div>
          </Card>
        )}
      </div>

      <TutorialAprovacoes open={tutorialAberto} onClose={fecharTutorial} />
    </div>
  );
}
