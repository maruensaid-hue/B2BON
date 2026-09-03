import { useState, type FormEvent } from "react";

import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Modal } from "@/components/ui/Modal";
import { api, ApiError } from "@/lib/api";

interface Turno {
  autor: "usuario" | "ia";
  texto: string;
}

interface FaqModalProps {
  open: boolean;
  onClose: () => void;
  onRefazerTour: () => void;
}

export function FaqModal({ open, onClose, onRefazerTour }: FaqModalProps) {
  const [pergunta, setPergunta] = useState("");
  const [turnos, setTurnos] = useState<Turno[]>([]);
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  async function enviarPergunta(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const texto = pergunta.trim();
    if (!texto || enviando) return;

    setErro(null);
    setTurnos((atual) => [...atual, { autor: "usuario", texto }]);
    setPergunta("");
    setEnviando(true);
    try {
      const resposta = await api.post<{ resposta: string }>("/faq/perguntar", { pergunta: texto });
      setTurnos((atual) => [...atual, { autor: "ia", texto: resposta.resposta }]);
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível obter uma resposta agora.");
    } finally {
      setEnviando(false);
    }
  }

  return (
    <Modal title="FAQ — Assistente da B2B ON" open={open} onClose={onClose}>
      <div className="flex flex-col gap-3">
        <Button size="sm" variant="ghost" onClick={onRefazerTour} className="self-start">
          🔄 Refazer o tour
        </Button>

        <div className="flex max-h-80 min-h-32 flex-col gap-2 overflow-y-auto rounded-lg border border-border bg-surf2 p-3">
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
                  : "self-start rounded-lg bg-surf px-3 py-2 text-[12px] text-text"
              }
            >
              {turno.texto}
            </div>
          ))}
          {enviando && <div className="self-start text-[12px] text-muted">Pensando...</div>}
        </div>

        {erro && <div className="text-[12px] text-red">{erro}</div>}

        <form onSubmit={enviarPergunta} className="flex gap-2">
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
    </Modal>
  );
}
