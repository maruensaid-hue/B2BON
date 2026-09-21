import { useState, type FormEvent } from "react";

import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { api, ApiError } from "@/lib/api";

interface Turno {
  autor: "usuario" | "ia";
  texto: string;
}

// Só os últimos turnos entram no histórico reenviado ao backend — mesmo
// limite de `_LIMITE_TURNOS_HISTORICO` em app/services/faq_service.py,
// mantido em sincronia manual (não há um único lugar pra compartilhar
// essa constante entre front e back nesta stack).
const LIMITE_TURNOS_HISTORICO = 6;

interface PainelAjudaDocadoProps {
  open: boolean;
  onOpen: () => void;
  onClose: () => void;
  onRefazerTour: () => void;
}

/** Painel de IA docado (raio-X 2026-09-21) — consolida o antigo
 * FaqModal num painel fixo na borda direita da tela, minimizado por
 * padrão (só a aba), que permanece aberto entre navegações até o
 * usuário fechar de novo. A transcrição não é persistida (fechar ou
 * recarregar a página limpa a conversa) — só o estado aberto/fechado
 * é salvo pelo componente pai (AppShell) em localStorage. */
export function PainelAjudaDocado({ open, onOpen, onClose, onRefazerTour }: PainelAjudaDocadoProps) {
  const [pergunta, setPergunta] = useState("");
  const [turnos, setTurnos] = useState<Turno[]>([]);
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  async function enviarPergunta(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const texto = pergunta.trim();
    if (!texto || enviando) return;

    const historico = turnos.slice(-LIMITE_TURNOS_HISTORICO);
    setErro(null);
    setTurnos((atual) => [...atual, { autor: "usuario", texto }]);
    setPergunta("");
    setEnviando(true);
    try {
      const resposta = await api.post<{ resposta: string }>("/faq/perguntar", {
        pergunta: texto,
        historico,
      });
      setTurnos((atual) => [...atual, { autor: "ia", texto: resposta.resposta }]);
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível obter uma resposta agora.");
    } finally {
      setEnviando(false);
    }
  }

  if (!open) {
    return (
      <button
        type="button"
        onClick={onOpen}
        title="Assistente da B2B ON"
        className="fixed right-5 bottom-5 z-[90] flex h-12 w-12 items-center justify-center rounded-full bg-cyan text-xl text-white shadow-xl transition-transform hover:scale-105"
      >
        💬
      </button>
    );
  }

  return (
    <div className="fixed top-0 right-0 bottom-0 z-[90] flex w-96 max-w-[92vw] flex-col border-l border-border bg-surf shadow-2xl">
      <div className="flex items-center justify-between border-b border-border p-3.5">
        <div>
          <div className="font-head text-[13px] font-bold text-text">Assistente da B2B ON</div>
          <button type="button" onClick={onRefazerTour} className="text-[11px] text-cyan hover:underline">
            🔄 Refazer o tour
          </button>
        </div>
        <button type="button" onClick={onClose} title="Fechar" className="text-[13px] text-muted hover:text-text">
          ✕
        </button>
      </div>

      <div className="flex flex-1 flex-col gap-2 overflow-y-auto p-3.5">
        {turnos.length === 0 && (
          <div className="text-[12px] text-muted">
            Pergunte qualquer coisa sobre como usar a plataforma — ex.: "Como eu ativo uma cadência?".
          </div>
        )}
        {turnos.map((turno, indice) => (
          <div
            key={indice}
            className={
              turno.autor === "usuario"
                ? "self-end rounded-lg bg-cyan/15 px-3 py-2 text-[12px] text-text"
                : "self-start rounded-lg bg-surf2 px-3 py-2 text-[12px] text-text"
            }
          >
            {turno.texto}
          </div>
        ))}
        {enviando && <div className="self-start text-[12px] text-muted">Pensando...</div>}
      </div>

      {erro && <div className="px-3.5 text-[12px] text-red">{erro}</div>}

      <form onSubmit={enviarPergunta} className="flex gap-2 border-t border-border p-3.5">
        <Input
          value={pergunta}
          onChange={(event) => setPergunta(event.target.value)}
          placeholder="Digite sua pergunta..."
          className="flex-1"
        />
        <Button type="submit" size="sm" disabled={enviando || !pergunta.trim()}>
          Enviar
        </Button>
      </form>
    </div>
  );
}
