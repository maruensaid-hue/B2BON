import { useEffect, useState } from "react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, SectionLabel } from "@/components/ui/Card";
import { Select } from "@/components/ui/Input";
import { Modal } from "@/components/ui/Modal";
import { api, ApiError } from "@/lib/api";

interface Reuniao {
  id: number;
  conta_id: number;
  conta_nome: string;
  decisor_id: number;
  decisor_nome: string;
  vendedor_id: string;
  data_hora: string;
  status: string;
  horarios_propostos: string[];
  horario_confirmado: string | null;
  link_reuniao: string | null;
  qualificada_confirmada: boolean | null;
}

interface Dossie {
  decisor_nome: string;
  conta_nome: string;
  dores: string[];
  respostas: { pergunta?: string; resposta?: string }[];
  score_total: number | null;
  score_criterios: Record<string, number>;
  proxima_acao_recomendada: string;
}

function toneStatus(status: string): "cyan" | "green" | "amber" | "red" | "muted" {
  if (status === "agendada") return "cyan";
  if (status === "realizada") return "green";
  if (status === "horarios_propostos") return "amber";
  if (status === "no_show" || status === "cancelada") return "red";
  return "muted";
}

export function Reunioes() {
  const [reunioes, setReunioes] = useState<Reuniao[]>([]);
  const [filtroStatus, setFiltroStatus] = useState("");
  const [dossieAberto, setDossieAberto] = useState<Dossie | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [mensagem, setMensagem] = useState<string | null>(null);

  async function carregar() {
    try {
      const params = filtroStatus ? `?status=${filtroStatus}` : "";
      setReunioes(await api.get<Reuniao[]>(`/reunioes${params}`));
    } catch {
      setErro("Não foi possível carregar as reuniões.");
    }
  }

  useEffect(() => {
    carregar();
  }, [filtroStatus]);

  async function confirmarHorario(reuniaoId: number, horario: string) {
    try {
      await api.post(`/reunioes/${reuniaoId}/confirmar`, { horario_escolhido: horario });
      setMensagem("Reunião confirmada.");
      await carregar();
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível confirmar a reunião.");
    }
  }

  async function marcarResultado(reuniaoId: number, status: "realizada" | "no_show") {
    try {
      await api.post(`/reunioes/${reuniaoId}/marcar-resultado`, { status });
      setMensagem("Resultado registrado.");
      await carregar();
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível marcar o resultado.");
    }
  }

  async function confirmarQualificacao(reuniaoId: number, qualificada: boolean) {
    try {
      await api.post(`/reunioes/${reuniaoId}/confirmar-qualificacao`, { qualificada, motivo: null });
      setMensagem("Qualificação registrada.");
      await carregar();
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível registrar a qualificação.");
    }
  }

  async function verDossie(reuniaoId: number) {
    try {
      setDossieAberto(await api.get<Dossie>(`/reunioes/${reuniaoId}/dossie`));
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível carregar o dossiê.");
    }
  }

  return (
    <div className="p-5.5">
      <div className="mb-5 flex items-end justify-between">
        <div>
          <div className="font-head text-xl font-bold">Reuniões</div>
          <div className="mt-0.5 text-[11px] text-muted">
            Horários propostos, confirmação, resultado e dossiê automático
          </div>
        </div>
        <Select value={filtroStatus} onChange={(event) => setFiltroStatus(event.target.value)} className="w-52">
          <option value="">Todos os status</option>
          <option value="horarios_propostos">Horários propostos</option>
          <option value="agendada">Agendada</option>
          <option value="realizada">Realizada</option>
          <option value="no_show">No-show</option>
          <option value="reagendada">Reagendada</option>
          <option value="cancelada">Cancelada</option>
        </Select>
      </div>

      {erro && <div className="mb-4 text-[12px] text-red">{erro}</div>}
      {mensagem && <div className="mb-4 text-[12px] text-green">{mensagem}</div>}

      <Card>
        <SectionLabel>Reuniões</SectionLabel>
        <div className="flex flex-col gap-2">
          {reunioes.map((reuniao) => (
            <div key={reuniao.id} className="rounded-lg border border-border p-3">
              <div className="mb-1.5 flex items-center justify-between">
                <div className="text-[12.5px] font-semibold">
                  {reuniao.conta_nome} — {reuniao.decisor_nome}
                </div>
                <Badge tone={toneStatus(reuniao.status)}>{reuniao.status}</Badge>
              </div>
              <div className="mb-2 text-[11px] text-muted">
                Vendedor: {reuniao.vendedor_id} ·{" "}
                {new Date(reuniao.horario_confirmado ?? reuniao.data_hora).toLocaleString("pt-BR")}
              </div>

              {reuniao.status === "horarios_propostos" && (
                <div className="flex flex-wrap gap-2">
                  {reuniao.horarios_propostos.map((horario) => (
                    <Button key={horario} size="sm" onClick={() => confirmarHorario(reuniao.id, horario)}>
                      Confirmar {new Date(horario).toLocaleString("pt-BR")}
                    </Button>
                  ))}
                </div>
              )}

              {reuniao.status === "agendada" && (
                <div className="flex gap-2">
                  <Button size="sm" variant="green" onClick={() => marcarResultado(reuniao.id, "realizada")}>
                    Marcar realizada
                  </Button>
                  <Button size="sm" variant="danger" onClick={() => marcarResultado(reuniao.id, "no_show")}>
                    Marcar no-show
                  </Button>
                </div>
              )}

              {reuniao.status === "realizada" && (
                <div className="flex flex-wrap items-center gap-2">
                  {reuniao.qualificada_confirmada === null ? (
                    <>
                      <span className="text-[11px] text-muted">Foi uma reunião qualificada?</span>
                      <Button size="sm" variant="green" onClick={() => confirmarQualificacao(reuniao.id, true)}>
                        Sim
                      </Button>
                      <Button size="sm" variant="danger" onClick={() => confirmarQualificacao(reuniao.id, false)}>
                        Não
                      </Button>
                    </>
                  ) : (
                    <Badge tone={reuniao.qualificada_confirmada ? "green" : "muted"}>
                      {reuniao.qualificada_confirmada ? "qualificada" : "não qualificada"}
                    </Badge>
                  )}
                  <Button size="sm" variant="ghost" onClick={() => verDossie(reuniao.id)}>
                    Ver dossiê
                  </Button>
                </div>
              )}
            </div>
          ))}
          {reunioes.length === 0 && <div className="text-[12px] text-muted">Nenhuma reunião ainda.</div>}
        </div>
      </Card>

      <Modal title="Dossiê da reunião" open={dossieAberto !== null} onClose={() => setDossieAberto(null)}>
        {dossieAberto && (
          <div className="flex flex-col gap-3 text-[12.5px]">
            <div>
              <span className="font-semibold">{dossieAberto.decisor_nome}</span> — {dossieAberto.conta_nome}
            </div>
            {dossieAberto.score_total !== null && (
              <div className="text-cyan">Score de qualificação: {dossieAberto.score_total}</div>
            )}
            {dossieAberto.dores.length > 0 && (
              <div>
                <div className="mb-1 text-[10px] tracking-wide text-muted uppercase">Dores levantadas</div>
                <ul className="list-inside list-disc text-muted">
                  {dossieAberto.dores.map((dor, indice) => (
                    <li key={indice}>{dor}</li>
                  ))}
                </ul>
              </div>
            )}
            <div>
              <div className="mb-1 text-[10px] tracking-wide text-muted uppercase">Próxima ação recomendada</div>
              <div>{dossieAberto.proxima_acao_recomendada}</div>
            </div>
          </div>
        )}
      </Modal>
    </div>
  );
}
