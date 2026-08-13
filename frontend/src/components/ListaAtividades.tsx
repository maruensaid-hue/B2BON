import { useState } from "react";

import { Button } from "@/components/ui/Button";
import { Select, Textarea } from "@/components/ui/Input";
import { ApiError } from "@/lib/api";

export interface Atividade {
  id: number;
  conta_id: number | null;
  negocio_id: number | null;
  usuario_id: number | null;
  tipo: string;
  descricao: string;
  criado_em: string;
}

export const ICONES_TIPO_ATIVIDADE: Record<string, string> = {
  ligacao: "📞",
  nota: "📝",
  reuniao: "📅",
  email: "✉️",
  whatsapp: "💬",
  linkedin: "🔗",
  tarefa: "✅",
  sistema: "🤖",
};

const TIPOS_REGISTRO_MANUAL = [
  { valor: "ligacao", rotulo: "Ligação" },
  { valor: "reuniao", rotulo: "Reunião" },
  { valor: "email", rotulo: "E-mail" },
  { valor: "whatsapp", rotulo: "WhatsApp" },
  { valor: "nota", rotulo: "Nota" },
];

interface Props {
  atividades: Atividade[];
  titulo?: string;
  /** Se informado, mostra o formulário de registro manual (ligação, reunião, e-mail, WhatsApp, nota). */
  aoRegistrar?: (tipo: string, descricao: string) => Promise<void>;
}

export function ListaAtividades({ atividades, titulo = "Atividades", aoRegistrar }: Props) {
  const [tipo, setTipo] = useState(TIPOS_REGISTRO_MANUAL[0].valor);
  const [descricao, setDescricao] = useState("");
  const [registrando, setRegistrando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  async function registrar() {
    if (!aoRegistrar || !descricao.trim() || registrando) return;
    setRegistrando(true);
    setErro(null);
    try {
      await aoRegistrar(tipo, descricao.trim());
      setDescricao("");
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível registrar a atividade.");
    } finally {
      setRegistrando(false);
    }
  }

  return (
    <div>
      <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">{titulo}</div>

      {aoRegistrar && (
        <div className="mb-3 flex flex-col gap-2 rounded-lg border border-border p-2.5">
          {erro && <div className="text-[11px] text-red">{erro}</div>}
          <Select value={tipo} onChange={(event) => setTipo(event.target.value)}>
            {TIPOS_REGISTRO_MANUAL.map((opcao) => (
              <option key={opcao.valor} value={opcao.valor}>
                {opcao.rotulo}
              </option>
            ))}
          </Select>
          <Textarea
            rows={2}
            value={descricao}
            onChange={(event) => setDescricao(event.target.value)}
            placeholder="O que aconteceu?"
          />
          <Button size="sm" type="button" disabled={registrando || !descricao.trim()} onClick={registrar}>
            {registrando ? "Registrando..." : "Registrar"}
          </Button>
        </div>
      )}

      {atividades.length === 0 ? (
        <div className="text-[11px] text-muted">Nenhuma atividade registrada ainda.</div>
      ) : (
        <div className="flex flex-col gap-1.5">
          {atividades.map((atividade) => (
            <div key={atividade.id} className="flex items-start gap-2 border-b border-border py-1 text-[11px]">
              <span>{ICONES_TIPO_ATIVIDADE[atividade.tipo] ?? "•"}</span>
              <div className="flex-1">
                <div className="text-text">{atividade.descricao}</div>
                <div className="text-muted">{new Date(atividade.criado_em).toLocaleString("pt-BR")}</div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
