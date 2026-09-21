import { useEffect, useState, type FormEvent } from "react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, SectionLabel } from "@/components/ui/Card";
import { Select, Textarea } from "@/components/ui/Input";
import { TutorialAgenteCorporativo } from "@/pages/agente-corporativo/TutorialAgenteCorporativo";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";

interface Evidencia {
  tipo: string;
  id: number;
  trecho: string;
}

interface PerguntaAgente {
  id: number;
  tenant_id_alvo: string;
  tenant_id_alvo_nome: string;
  tenant_id_perguntante: string;
  tenant_id_perguntante_nome: string;
  pergunta: string;
  resposta_rascunho: string | null;
  resposta_final: string | null;
  evidencias: Evidencia[];
  status: "pendente_aprovacao" | "aprovada" | "editada" | "recusada";
  criado_em: string;
  respondido_em: string | null;
}

const ROTULO_MODO: Record<string, string> = {
  disabled: "Desabilitado",
  interno: "Interno (testar sem expor à rede)",
  assistido: "Assistido (outras empresas podem perguntar)",
};

const ROTULO_STATUS: Record<string, { texto: string; tone: "green" | "amber" | "muted" | "red" }> = {
  pendente_aprovacao: { texto: "Aguardando aprovação", tone: "amber" },
  aprovada: { texto: "Aprovada", tone: "green" },
  editada: { texto: "Aprovada (editada)", tone: "green" },
  recusada: { texto: "Recusada", tone: "red" },
};

export function AgenteCorporativo() {
  const { usuario, marcarTutorialModuloVisto } = useAuth();
  // Tutorial do módulo (raio-X 2026-09-21) — abre sozinho na primeira
  // visita, coexiste com o tour grande.
  const [tutorialAberto, setTutorialAberto] = useState(false);
  const [carregado, setCarregado] = useState(false);
  useEffect(() => {
    if (usuario && carregado && !(usuario.tutoriais_modulo_vistos ?? []).includes("agente-corporativo")) {
      setTutorialAberto(true);
    }
  }, [usuario, carregado]);
  function fecharTutorial() {
    setTutorialAberto(false);
    if (usuario && !(usuario.tutoriais_modulo_vistos ?? []).includes("agente-corporativo")) {
      marcarTutorialModuloVisto("agente-corporativo");
    }
  }
  const [modo, setModo] = useState("disabled");
  const [salvandoModo, setSalvandoModo] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  const [perguntaTeste, setPerguntaTeste] = useState("");
  const [testando, setTestando] = useState(false);
  const [resultadoTeste, setResultadoTeste] = useState<{ resposta: string; evidencias: Evidencia[] } | null>(null);

  const [pendentes, setPendentes] = useState<PerguntaAgente[]>([]);
  const [minhasPerguntas, setMinhasPerguntas] = useState<PerguntaAgente[]>([]);
  const [respostasEditadas, setRespostasEditadas] = useState<Record<number, string>>({});
  const [processandoId, setProcessandoId] = useState<number | null>(null);

  async function carregar() {
    try {
      const [modoResp, pendentesResp, minhasResp] = await Promise.all([
        api.get<{ modo: string }>("/agente-corporativo/modo"),
        api.get<PerguntaAgente[]>("/agente-corporativo/pendentes"),
        api.get<PerguntaAgente[]>("/agente-corporativo/minhas-perguntas"),
      ]);
      setModo(modoResp.modo);
      setPendentes(pendentesResp);
      setMinhasPerguntas(minhasResp);
    } catch {
      setErro("Não foi possível carregar o Agente Corporativo.");
    } finally {
      setCarregado(true);
    }
  }

  useEffect(() => {
    carregar();
  }, []);

  async function salvarModo(novoModo: string) {
    setSalvandoModo(true);
    setErro(null);
    try {
      await api.put("/agente-corporativo/modo", { modo: novoModo });
      setModo(novoModo);
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível salvar o modo do agente.");
    } finally {
      setSalvandoModo(false);
    }
  }

  async function testarAgente(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (testando || !perguntaTeste.trim()) return;
    setTestando(true);
    setErro(null);
    try {
      setResultadoTeste(await api.post("/agente-corporativo/testar", { pergunta: perguntaTeste.trim() }));
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível testar o agente.");
    } finally {
      setTestando(false);
    }
  }

  async function aprovar(perguntaId: number) {
    setProcessandoId(perguntaId);
    setErro(null);
    try {
      const respostaEditada = respostasEditadas[perguntaId]?.trim();
      await api.post(`/agente-corporativo/pendentes/${perguntaId}/aprovar`, {
        resposta_final: respostaEditada || null,
      });
      await carregar();
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível aprovar esta resposta.");
    } finally {
      setProcessandoId(null);
    }
  }

  async function recusar(perguntaId: number) {
    setProcessandoId(perguntaId);
    setErro(null);
    try {
      await api.post(`/agente-corporativo/pendentes/${perguntaId}/recusar`, {});
      await carregar();
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível recusar esta pergunta.");
    } finally {
      setProcessandoId(null);
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <div>
        <div className="flex items-center gap-2">
          <h1 className="font-head text-[22px] font-extrabold text-text">Agente Corporativo</h1>
          <button type="button" onClick={() => setTutorialAberto(true)} className="text-[11px] text-muted hover:text-cyan">
            🔄 Rever tutorial
          </button>
        </div>
        <p className="text-[13px] text-muted">
          Um agente de IA que responde perguntas de outras empresas da rede, só com base no que você cadastrou —
          sempre revisado por um humano antes de sair.
        </p>
      </div>

      {erro && <div className="rounded-lg border border-red/30 bg-red/10 p-3 text-[12px] text-red">{erro}</div>}

      <Card data-tutorial-id="agente-corporativo:modo">
        <SectionLabel>Configurar seu agente</SectionLabel>
        <p className="mb-3 text-[12px] text-muted">
          "Interno" deixa você testar o agente sem expor às outras empresas. "Assistido" permite que empresas
          conectadas perguntem — a IA rascunha, mas a resposta só é enviada depois que você aprovar ou editar.
        </p>
        <div className="w-[360px]">
          <Select value={modo} disabled={salvandoModo} onChange={(event) => salvarModo(event.target.value)}>
            {Object.entries(ROTULO_MODO).map(([valor, rotulo]) => (
              <option key={valor} value={valor}>
                {rotulo}
              </option>
            ))}
          </Select>
        </div>
      </Card>

      <Card data-tutorial-id="agente-corporativo:testar">
        <SectionLabel>Testar seu agente</SectionLabel>
        <p className="mb-3 text-[12px] text-muted">
          Simula uma pergunta de outra empresa — não fica visível pra ninguém, é só pra você validar o que o agente
          responderia com base nas suas Ofertas, Perfil e FAQ cadastrados.
        </p>
        <form onSubmit={testarAgente} className="flex flex-col gap-2">
          <Textarea
            value={perguntaTeste}
            onChange={(event) => setPerguntaTeste(event.target.value)}
            placeholder="Ex: Vocês têm solução de backup imutável?"
            rows={2}
          />
          <Button type="submit" disabled={testando || modo === "disabled"} className="w-fit">
            {testando ? "Testando..." : "Testar"}
          </Button>
          {modo === "disabled" && <div className="text-[11px] text-muted">Ative o modo interno ou assistido para testar.</div>}
        </form>
        {resultadoTeste && (
          <div className="mt-3 rounded-lg bg-surf2 p-3 text-[12px]">
            <div className="text-text">{resultadoTeste.resposta}</div>
            {resultadoTeste.evidencias.length > 0 && (
              <div className="mt-2 text-muted">
                Evidências usadas: {resultadoTeste.evidencias.map((evidencia) => evidencia.trecho).join(" · ")}
              </div>
            )}
          </div>
        )}
      </Card>

      <Card data-tutorial-id="agente-corporativo:pendentes">
        <SectionLabel>Perguntas recebidas</SectionLabel>
        <p className="mb-3 text-[12px] text-muted">
          Empresas conectadas perguntaram ao seu agente — revise o rascunho da IA, edite se precisar, e só então
          aprove ou recuse.
        </p>
        <div className="flex flex-col gap-3">
          {pendentes.map((pergunta) => (
            <div key={pergunta.id} className="rounded-lg border border-border p-3 text-[12px]">
              <div className="mb-1 font-semibold text-text">
                {pergunta.tenant_id_perguntante_nome} perguntou: "{pergunta.pergunta}"
              </div>
              <Textarea
                defaultValue={pergunta.resposta_rascunho ?? ""}
                onChange={(event) =>
                  setRespostasEditadas((atual) => ({ ...atual, [pergunta.id]: event.target.value }))
                }
                rows={3}
              />
              <div className="mt-2 flex gap-2">
                <Button size="sm" onClick={() => aprovar(pergunta.id)} disabled={processandoId === pergunta.id}>
                  {processandoId === pergunta.id ? "Processando..." : "Aprovar"}
                </Button>
                <Button size="sm" variant="ghost" onClick={() => recusar(pergunta.id)} disabled={processandoId === pergunta.id}>
                  Recusar
                </Button>
              </div>
            </div>
          ))}
          {pendentes.length === 0 && <div className="text-[12px] text-muted">Nenhuma pergunta aguardando aprovação.</div>}
        </div>
      </Card>

      <Card>
        <SectionLabel>Minhas perguntas</SectionLabel>
        <p className="mb-3 text-[12px] text-muted">Perguntas que você fez ao agente de outras empresas.</p>
        <div className="flex flex-col gap-2">
          {minhasPerguntas.map((pergunta) => {
            const status = ROTULO_STATUS[pergunta.status] ?? ROTULO_STATUS.pendente_aprovacao;
            return (
              <div key={pergunta.id} className="rounded-lg border border-border p-3 text-[12px]">
                <div className="mb-1 flex items-center justify-between">
                  <span className="font-semibold text-text">{pergunta.tenant_id_alvo_nome}</span>
                  <Badge tone={status.tone}>{status.texto}</Badge>
                </div>
                <div className="text-muted">Pergunta: {pergunta.pergunta}</div>
                {pergunta.resposta_final && <div className="mt-1 text-text">Resposta: {pergunta.resposta_final}</div>}
              </div>
            );
          })}
          {minhasPerguntas.length === 0 && <div className="text-[12px] text-muted">Você ainda não perguntou a nenhuma empresa.</div>}
        </div>
      </Card>

      <TutorialAgenteCorporativo open={tutorialAberto} onClose={fecharTutorial} />
    </div>
  );
}
