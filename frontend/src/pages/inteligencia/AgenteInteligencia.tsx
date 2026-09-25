import { useEffect, useState, type FormEvent } from "react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, SectionLabel } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { api, ApiError } from "@/lib/api";

interface Ferramenta {
  ferramenta: string;
  agente: string;
  sensibilidade: string;
  exemplo: string;
}

interface Resposta {
  status: string;
  agente: string | null;
  ferramenta: string | null;
  roteamento: string;
  resposta: string;
  resultado: Record<string, unknown> | null;
}

const TOM: Record<string, "green" | "amber" | "red" | "muted"> = {
  OK: "green",
  PROPOSTA_REQUER_CONFIRMACAO: "amber",
  ESCLARECER: "amber",
  FALTAM_PARAMETROS: "amber",
  RECUSADO: "red",
  SEM_FERRAMENTA: "muted",
};

/** B2B ON Intelligence Agent (Fase 12): uma pergunta, o agente certo. Só
 * lê; ações que mudam dados viram proposta para você confirmar. */
export function AgenteInteligencia() {
  const [ferramentas, setFerramentas] = useState<Ferramenta[]>([]);
  const [resposta, setResposta] = useState<Resposta | null>(null);
  const [perguntando, setPerguntando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => {
    api
      .get<Ferramenta[]>("/inteligencia/agente/ferramentas")
      .then(setFerramentas)
      .catch(() => setFerramentas([]));
  }, []);

  async function perguntar(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const pergunta = String(
      new FormData(event.currentTarget).get("pergunta") ?? "",
    );
    setPerguntando(true);
    setErro(null);
    try {
      setResposta(
        await api.post<Resposta>("/inteligencia/agente", { pergunta }),
      );
    } catch (error) {
      setErro(
        error instanceof ApiError
          ? error.message
          : "Não foi possível consultar o agente.",
      );
    } finally {
      setPerguntando(false);
    }
  }

  const exemplos = ferramentas.map((f) => f.exemplo).filter(Boolean);

  return (
    <Card className="mb-4" data-testid="agente-inteligencia">
      <SectionLabel>B2B ON Intelligence Agent</SectionLabel>
      <div className="mb-2 text-[11px] text-muted">
        Pergunte em português. O agente escolhe o especialista e responde com os
        dados do seu plano; ações que mudam dados nunca são executadas por ele.
      </div>
      <form onSubmit={perguntar} className="flex gap-2">
        <Input
          name="pergunta"
          required
          minLength={3}
          placeholder={exemplos[0] ?? "Faça uma pergunta"}
          className="flex-1"
        />
        <Button type="submit" disabled={perguntando}>
          {perguntando ? "Pensando..." : "Perguntar"}
        </Button>
      </form>
      {exemplos.length > 0 && (
        <div className="mt-1.5 text-[10px] text-muted">
          Exemplos: {exemplos.slice(0, 4).join(" · ")}
        </div>
      )}
      {erro && <div className="mt-2 text-[11px] text-red">{erro}</div>}
      {resposta && (
        <div className="mt-3 rounded-md border border-border p-2 text-[11px]">
          <div className="flex flex-wrap items-center gap-2">
            <Badge tone={TOM[resposta.status] ?? "muted"}>
              {resposta.status}
            </Badge>
            {resposta.agente && (
              <span className="text-muted">agente: {resposta.agente}</span>
            )}
            {resposta.ferramenta && (
              <span className="text-muted">· {resposta.ferramenta}</span>
            )}
            <span className="text-muted">
              · roteado por{" "}
              {resposta.roteamento === "ia" ? "IA" : "palavras-chave"}
            </span>
          </div>
          <div className="mt-1 text-text">{resposta.resposta}</div>
          {resposta.resultado && (
            <details className="mt-1">
              <summary className="cursor-pointer text-[10px] text-cyan">
                Dados
              </summary>
              <pre className="mt-1 max-h-60 overflow-auto text-[10px] whitespace-pre-wrap text-muted">
                {JSON.stringify(resposta.resultado, null, 2)}
              </pre>
            </details>
          )}
        </div>
      )}
    </Card>
  );
}
