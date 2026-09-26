import { useCallback, useEffect, useState, type FormEvent } from "react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Input, Select } from "@/components/ui/Input";
import { Modal } from "@/components/ui/Modal";
import { toneClassificacao } from "@/pages/map/risco";
import { api, ApiError } from "@/lib/api";

interface ScoreRisco {
  score: number;
  classificacao: string;
  dias_sem_contato: number | null;
  sinais: Record<string, number>;
}

interface Interacao {
  id: number;
  tipo: string;
  descricao: string | null;
  criado_em: string;
}

interface ScriptResgate {
  script: string;
  justificativa: string;
}

const TIPOS_INTERACAO = [
  { valor: "contato", rotulo: "Contato" },
  { valor: "ticket_suporte", rotulo: "Ticket de Suporte" },
  { valor: "reclamacao", rotulo: "Reclamação" },
  { valor: "feedback_positivo", rotulo: "Feedback Positivo" },
  { valor: "reuniao_remarcada", rotulo: "Reunião Remarcada" },
  { valor: "mencionou_concorrente", rotulo: "Mencionou Concorrente" },
];

/** Detalhe de risco do MAP — o mesmo para conta (MapContas) e tenant (MapTenants): score com sinais,
 * script de resgate, histórico e registro de interação. `base` é o recurso (`.../score-risco`,
 * `.../interacoes`, `.../script-resgate`); `interacao` diz onde gravar e a chave do alvo. */
export function DetalheRisco({
  base,
  interacao,
  aoRegistrar,
  aoErro,
}: {
  base: string;
  interacao: { caminho: string; alvo: Record<string, string | number> };
  aoRegistrar: () => Promise<unknown> | void;
  aoErro: (mensagem: string) => void;
}) {
  const [scoreRisco, setScoreRisco] = useState<ScoreRisco | null>(null);
  const [interacoes, setInteracoes] = useState<Interacao[]>([]);
  const [script, setScript] = useState<ScriptResgate | null>(null);
  const [modalAberto, setModalAberto] = useState(false);
  const [gerandoScript, setGerandoScript] = useState(false);

  const carregar = useCallback(async () => {
    try {
      const [scoreResp, interacoesResp] = await Promise.all([
        api.get<ScoreRisco>(`${base}/score-risco`),
        api.get<Interacao[]>(`${base}/interacoes`),
      ]);
      setScoreRisco(scoreResp);
      setInteracoes(interacoesResp);
    } catch (error) {
      aoErro(error instanceof ApiError ? error.message : "Não foi possível carregar o detalhe.");
    }
  }, [base, aoErro]);

  useEffect(() => {
    setScript(null);
    carregar();
  }, [carregar]);

  async function registrarInteracao(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    try {
      await api.post(interacao.caminho, {
        ...interacao.alvo,
        tipo: String(form.get("tipo")),
        descricao: String(form.get("descricao") || "") || null,
      });
      setModalAberto(false);
      await Promise.all([carregar(), aoRegistrar()]);
    } catch (error) {
      aoErro(error instanceof ApiError ? error.message : "Não foi possível registrar a interação.");
    }
  }

  async function gerarScript() {
    setGerandoScript(true);
    try {
      setScript(await api.get<ScriptResgate>(`${base}/script-resgate`));
    } catch (error) {
      aoErro(error instanceof ApiError ? error.message : "Não foi possível gerar o script de resgate.");
    } finally {
      setGerandoScript(false);
    }
  }

  if (!scoreRisco) return null;
  return (
    <>
      <div className="mb-3 flex items-center gap-2">
        <Badge tone={toneClassificacao(scoreRisco.classificacao)}>
          {scoreRisco.classificacao} · {scoreRisco.score.toFixed(0)}/100
        </Badge>
        {scoreRisco.dias_sem_contato !== null && (
          <span className="text-[11px] text-muted">{scoreRisco.dias_sem_contato}d sem contato</span>
        )}
      </div>

      {Object.keys(scoreRisco.sinais).length > 0 && (
        <div className="mb-3 text-[11px] text-muted">
          {Object.entries(scoreRisco.sinais).map(([sinal, pontos]) => (
            <div key={sinal}>
              {sinal}: {pontos > 0 ? "+" : ""}
              {pontos}
            </div>
          ))}
        </div>
      )}

      <div className="mb-3 flex gap-2">
        <Button size="sm" onClick={() => setModalAberto(true)}>
          Registrar interação
        </Button>
        <Button size="sm" variant="amber" disabled={gerandoScript} onClick={gerarScript}>
          {gerandoScript ? "Gerando..." : "Gerar script de resgate"}
        </Button>
      </div>

      {script && (
        <div className="mb-3 rounded-lg border border-border bg-surf2 p-3 text-[12px] leading-relaxed whitespace-pre-wrap">
          {script.script}
          <div className="mt-2 border-t border-border pt-2 text-[11px] text-muted">{script.justificativa}</div>
          <Button size="sm" className="mt-2" onClick={() => navigator.clipboard.writeText(script.script)}>
            Copiar
          </Button>
        </div>
      )}

      <div>
        <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">Histórico de interações</div>
        <div className="flex flex-col gap-1 text-[11px]">
          {interacoes.map((item) => (
            <div key={item.id} className="border-b border-border py-1">
              <span className="font-semibold text-text">{item.tipo}</span>
              {item.descricao && <span className="text-muted"> — {item.descricao}</span>}
            </div>
          ))}
          {interacoes.length === 0 && <div className="text-muted">Nenhuma interação registrada.</div>}
        </div>
      </div>

      <Modal title="Registrar interação" open={modalAberto} onClose={() => setModalAberto(false)}>
        <form onSubmit={registrarInteracao} className="flex flex-col gap-3">
          <div>
            <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">Tipo</div>
            <Select name="tipo" required defaultValue="">
              <option value="" disabled>
                Selecione...
              </option>
              {TIPOS_INTERACAO.map((tipo) => (
                <option key={tipo.valor} value={tipo.valor}>
                  {tipo.rotulo}
                </option>
              ))}
            </Select>
          </div>
          <div>
            <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">Descrição (opcional)</div>
            <Input name="descricao" />
          </div>
          <Button type="submit" className="w-full justify-center">
            Registrar
          </Button>
        </form>
      </Modal>
    </>
  );
}
