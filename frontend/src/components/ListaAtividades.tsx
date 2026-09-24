import { useMemo, useState } from "react";

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

type TomAtividade = "cyan" | "violet" | "green" | "amber" | "muted";

// Raio-X 2026-09-24: mesma paleta de `Badge.tsx` (`toneClasses`), mas
// aplicada numa bolha de ícone em vez de um pill — dá pra escanear o
// tipo de atividade sem ler o texto.
const TOM_TIPO_ATIVIDADE: Record<string, TomAtividade> = {
  ligacao: "cyan",
  reuniao: "violet",
  email: "cyan",
  whatsapp: "green",
  linkedin: "violet",
  tarefa: "amber",
  nota: "muted",
  sistema: "muted",
};

const CLASSES_TOM: Record<TomAtividade, string> = {
  cyan: "bg-cyan/15 text-cyan",
  violet: "bg-violet/15 text-violet",
  green: "bg-green/15 text-green",
  amber: "bg-amber/15 text-amber",
  muted: "bg-muted/10 text-muted",
};

const ROTULO_TIPO_ATIVIDADE: Record<string, string> = {
  ligacao: "Ligação",
  nota: "Nota",
  reuniao: "Reunião",
  email: "E-mail",
  whatsapp: "WhatsApp",
  linkedin: "LinkedIn",
  tarefa: "Tarefa",
  sistema: "Sistema",
};

const TIPOS_REGISTRO_MANUAL = [
  { valor: "ligacao", rotulo: "Ligação" },
  { valor: "reuniao", rotulo: "Reunião" },
  { valor: "email", rotulo: "E-mail" },
  { valor: "whatsapp", rotulo: "WhatsApp" },
  { valor: "nota", rotulo: "Nota" },
];

/** Chave de agrupamento por dia LOCAL — nunca `toISOString()` (mesmo
 * bug real já corrigido em `Agenda.tsx::chaveDia`: converte pra UTC
 * antes de extrair a data, deslocando o dia em fusos negativos). */
function chaveDiaLocal(data: Date): string {
  return `${data.getFullYear()}-${String(data.getMonth() + 1).padStart(2, "0")}-${String(data.getDate()).padStart(2, "0")}`;
}

function rotuloGrupoData(data: Date): string {
  const hoje = new Date();
  const ontem = new Date(hoje);
  ontem.setDate(ontem.getDate() - 1);
  if (chaveDiaLocal(data) === chaveDiaLocal(hoje)) return "Hoje";
  if (chaveDiaLocal(data) === chaveDiaLocal(ontem)) return "Ontem";
  return data.toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit", year: "numeric" });
}

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

  // Agrupamento por dia local, preservando a ordem que já vem da API
  // (mais recente primeiro) — não reordena, só junta visualmente.
  const gruposPorDia = useMemo(() => {
    const grupos: { chave: string; data: Date; itens: Atividade[] }[] = [];
    for (const atividade of atividades) {
      const data = new Date(atividade.criado_em);
      const chave = chaveDiaLocal(data);
      const ultimoGrupo = grupos[grupos.length - 1];
      if (ultimoGrupo && ultimoGrupo.chave === chave) {
        ultimoGrupo.itens.push(atividade);
      } else {
        grupos.push({ chave, data, itens: [atividade] });
      }
    }
    return grupos;
  }, [atividades]);

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
        <div className="flex flex-col gap-3">
          {gruposPorDia.map((grupo) => (
            <div key={grupo.chave}>
              <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">{rotuloGrupoData(grupo.data)}</div>
              <div className="flex flex-col gap-2">
                {grupo.itens.map((atividade) => {
                  const tom = TOM_TIPO_ATIVIDADE[atividade.tipo] ?? "muted";
                  return (
                    <div key={atividade.id} className="flex items-start gap-2.5 text-[11px]">
                      <span
                        className={`flex h-6 w-6 flex-shrink-0 items-center justify-center rounded-full text-[12px] ${CLASSES_TOM[tom]}`}
                      >
                        {ICONES_TIPO_ATIVIDADE[atividade.tipo] ?? "•"}
                      </span>
                      <div className="flex-1 border-b border-border pb-2">
                        <div className="flex items-baseline justify-between gap-2">
                          <span className="font-semibold text-text">
                            {ROTULO_TIPO_ATIVIDADE[atividade.tipo] ?? atividade.tipo}
                          </span>
                          <span className="flex-shrink-0 text-[10px] text-muted">
                            {new Date(atividade.criado_em).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" })}
                          </span>
                        </div>
                        <div className="mt-0.5 text-text">{atividade.descricao}</div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
