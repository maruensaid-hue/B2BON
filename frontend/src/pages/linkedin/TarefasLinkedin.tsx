import { useEffect, useState } from "react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { api, ApiError } from "@/lib/api";

// Avisa o menu (contador ao lado de "Tarefas de LinkedIn") que a quantidade de pendentes mudou.
export const EVENTO_TAREFAS_LINKEDIN = "b2bon:tarefas-linkedin";

interface TarefaLinkedin {
  id: number;
  mensagem_id: number;
  decisor_id: number;
  texto: string;
  link_perfil: string | null;
  status: "pendente" | "executada" | "ignorada";
  criado_em: string;
  decisor_nome: string | null;
  decisor_cargo: string | null;
  conta_id: number | null;
  conta_nome: string | null;
}

const FILTROS: { valor: string; rotulo: string }[] = [
  { valor: "pendente", rotulo: "Pendentes" },
  { valor: "executada", rotulo: "Enviadas" },
  { valor: "ignorada", rotulo: "Ignoradas" },
];

const TOM_STATUS: Record<string, "amber" | "green" | "muted"> = { pendente: "amber", executada: "green", ignorada: "muted" };
const ROTULO_STATUS: Record<string, string> = { pendente: "Pendente", executada: "Enviada", ignorada: "Ignorada" };

/** Endereço do perfil só se for um link web de verdade (nunca `javascript:` ou similar): aceita "linkedin.com/in/fulano" sem o https. */
function urlDoPerfil(link: string | null): string | null {
  const texto = (link ?? "").trim();
  if (!texto) return null;
  const comProtocolo = /^https?:\/\//i.test(texto) ? texto : `https://${texto.replace(/^\/+/, "")}`;
  try {
    const url = new URL(comProtocolo);
    return url.protocol === "https:" || url.protocol === "http:" ? url.toString() : null;
  } catch {
    return null;
  }
}

export function TarefasLinkedin() {
  const [filtro, setFiltro] = useState("pendente");
  const [tarefas, setTarefas] = useState<TarefaLinkedin[] | null>(null);
  const [copiadaId, setCopiadaId] = useState<number | null>(null);
  const [confirmandoIgnorarId, setConfirmandoIgnorarId] = useState<number | null>(null);
  const [processandoId, setProcessandoId] = useState<number | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [mensagem, setMensagem] = useState<string | null>(null);

  async function carregar(status: string) {
    try {
      setTarefas(await api.get<TarefaLinkedin[]>(`/linkedin/tarefas?status=${status}`));
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível carregar as tarefas de LinkedIn.");
    }
  }

  useEffect(() => {
    setTarefas(null);
    setConfirmandoIgnorarId(null);
    carregar(filtro);
  }, [filtro]);

  async function copiar(tarefa: TarefaLinkedin) {
    setErro(null);
    try {
      await navigator.clipboard.writeText(tarefa.texto);
      setCopiadaId(tarefa.id);
      window.setTimeout(() => setCopiadaId((atual) => (atual === tarefa.id ? null : atual)), 2500);
    } catch {
      setErro("Não foi possível copiar automaticamente. Clique no texto da mensagem para selecioná-lo e copie com Ctrl+C.");
    }
  }

  async function marcar(tarefa: TarefaLinkedin, executada: boolean) {
    if (processandoId !== null) return;
    setProcessandoId(tarefa.id);
    setErro(null);
    setMensagem(null);
    try {
      await api.post(`/linkedin/tarefas/${tarefa.id}/marcar`, { executada });
      setConfirmandoIgnorarId(null);
      setMensagem(
        executada
          ? `Marcada como enviada${tarefa.decisor_nome ? ` para ${tarefa.decisor_nome}` : ""} e registrada no histórico da conta.`
          : "Tarefa ignorada: a mensagem foi cancelada e não será enviada.",
      );
      await carregar(filtro);
      window.dispatchEvent(new Event(EVENTO_TAREFAS_LINKEDIN));
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível atualizar a tarefa.");
    } finally {
      setProcessandoId(null);
    }
  }

  return (
    <div className="p-5.5">
      <div className="mb-4">
        <div className="font-head text-xl font-bold">Tarefas de LinkedIn</div>
        <div className="mt-0.5 text-[11px] text-muted">Mensagens de LinkedIn das suas cadências, prontas para você enviar</div>
      </div>

      <Card className="mb-4">
        <div className="text-[12px] text-muted">
          O B2B ON <strong className="text-text">não envia mensagens pelo LinkedIn</strong>: automatizar o envio na sua conta pode levar à restrição
          dela. O sistema prepara a mensagem de cada toque e você faz o último passo:
        </div>
        <ol className="mt-2 list-decimal pl-5 text-[12px] text-muted">
          <li>Clique em <strong className="text-text">Copiar mensagem</strong>.</li>
          <li>Clique em <strong className="text-text">Abrir perfil</strong> (abre numa nova aba) e envie a mensagem pelo LinkedIn.</li>
          <li>Volte e clique em <strong className="text-text">Marcar como enviada</strong>. Isso atualiza a cadência e o histórico da conta.</li>
        </ol>
      </Card>

      {erro && <div className="mb-3 text-[12px] text-red">{erro}</div>}
      {mensagem && <div className="mb-3 text-[12px] text-green">{mensagem}</div>}

      <div className="mb-3 flex flex-wrap gap-1.5">
        {FILTROS.map((opcao) => (
          <Button key={opcao.valor} size="sm" variant={filtro === opcao.valor ? "primary" : "ghost"} onClick={() => setFiltro(opcao.valor)}>
            {opcao.rotulo}
            {tarefas && filtro === opcao.valor ? ` (${tarefas.length})` : ""}
          </Button>
        ))}
      </div>

      {tarefas === null && !erro && <div className="text-[12px] text-muted">Carregando...</div>}
      {tarefas && tarefas.length === 0 && (
        <div className="text-[12px] text-muted">
          {filtro === "pendente"
            ? "Nenhuma tarefa pendente. Elas aparecem aqui quando um toque de LinkedIn da cadência chega na hora de ser enviado."
            : "Nenhuma tarefa nesta lista."}
        </div>
      )}

      <div className="flex flex-col gap-3">
        {tarefas?.map((tarefa) => {
          const perfil = urlDoPerfil(tarefa.link_perfil);
          const ocupada = processandoId === tarefa.id;
          return (
            <Card key={tarefa.id}>
              <div className="mb-2 flex flex-wrap items-start justify-between gap-2">
                <div>
                  <div className="text-[13px] font-semibold text-text">{tarefa.decisor_nome ?? `Contato #${tarefa.decisor_id}`}</div>
                  <div className="text-[11px] text-muted">
                    {[tarefa.decisor_cargo, tarefa.conta_nome].filter(Boolean).join(" · ") || "Sem cargo ou empresa cadastrados"}
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <Badge tone={TOM_STATUS[tarefa.status]}>{ROTULO_STATUS[tarefa.status]}</Badge>
                  <span className="text-[10px] text-muted">{new Date(tarefa.criado_em).toLocaleDateString("pt-BR")}</span>
                </div>
              </div>

              <div
                className="mb-3 cursor-text rounded-lg bg-surf2 p-3 text-[12px] whitespace-pre-wrap text-text select-all"
                title="Clique para selecionar o texto todo"
              >
                {tarefa.texto}
              </div>

              {tarefa.status === "pendente" ? (
                <div className="flex flex-wrap items-center gap-2">
                  <Button size="sm" variant="ghost" onClick={() => copiar(tarefa)}>
                    {copiadaId === tarefa.id ? "✓ Copiada" : "Copiar mensagem"}
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    disabled={perfil === null}
                    title={perfil === null ? "Este contato não tem link de perfil do LinkedIn cadastrado" : undefined}
                    onClick={() => perfil && window.open(perfil, "_blank", "noopener,noreferrer")}
                  >
                    Abrir perfil
                  </Button>
                  {perfil === null && <span className="text-[10px] text-muted">sem link de perfil cadastrado</span>}
                  <span className="flex-1" />
                  <Button size="sm" disabled={ocupada} onClick={() => marcar(tarefa, true)}>
                    {ocupada ? "Salvando..." : "Marcar como enviada"}
                  </Button>
                  {confirmandoIgnorarId === tarefa.id ? (
                    <>
                      <span className="text-[11px] text-muted">A mensagem será cancelada. Ignorar?</span>
                      <Button size="sm" variant="danger" disabled={ocupada} onClick={() => marcar(tarefa, false)}>
                        Confirmar
                      </Button>
                      <Button size="sm" variant="ghost" onClick={() => setConfirmandoIgnorarId(null)}>
                        Cancelar
                      </Button>
                    </>
                  ) : (
                    <Button size="sm" variant="ghost" onClick={() => setConfirmandoIgnorarId(tarefa.id)}>
                      Ignorar
                    </Button>
                  )}
                </div>
              ) : (
                tarefa.conta_id !== null && <div className="text-[11px] text-muted">Registrada no histórico da conta {tarefa.conta_nome ?? `#${tarefa.conta_id}`}.</div>
              )}
            </Card>
          );
        })}
      </div>
    </div>
  );
}
