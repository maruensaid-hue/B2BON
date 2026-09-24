import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { api } from "@/lib/api";

interface ReuniaoAgenda {
  id: number;
  conta_id: number;
  conta_nome: string;
  decisor_nome: string;
  data_hora: string;
  status: string;
  horario_confirmado: string | null;
}

const DIAS_SEMANA = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"];

function toneStatus(status: string): "cyan" | "green" | "amber" | "red" | "muted" {
  if (status === "agendada") return "cyan";
  if (status === "realizada") return "green";
  if (status === "horarios_propostos") return "amber";
  if (status === "no_show" || status === "cancelada") return "red";
  return "muted";
}

function segundaFeiraDaSemana(data: Date): Date {
  const copia = new Date(data);
  const diaSemana = copia.getDay(); // 0 = domingo
  const deslocamento = diaSemana === 0 ? -6 : 1 - diaSemana;
  copia.setDate(copia.getDate() + deslocamento);
  copia.setHours(0, 0, 0, 0);
  return copia;
}

function adicionarDias(data: Date, dias: number): Date {
  const copia = new Date(data);
  copia.setDate(copia.getDate() + dias);
  return copia;
}

function chaveDia(data: Date): string {
  // Agrupamento por dia LOCAL, não UTC (bug real: `toISOString()`
  // convertia pra UTC e uma reunião marcada às 22h+ no fuso do Brasil
  // aparecia sob o dia seguinte, já que UTC vira meia-noite mais cedo).
  const ano = data.getFullYear();
  const mes = String(data.getMonth() + 1).padStart(2, "0");
  const dia = String(data.getDate()).padStart(2, "0");
  return `${ano}-${mes}-${dia}`;
}

/** Agenda (raio-X 2026-09-22) — visão semanal de compromissos (Reuniao),
 * item de menu novo e separado da página "Reuniões" (que continua sendo
 * a lista/gestão de status). Busca por intervalo de data a cada troca de
 * semana — GET /reunioes?data_inicio=&data_fim= (novo filtro no
 * backend), nunca carrega o histórico inteiro do tenant de uma vez. */
export function Agenda() {
  const navigate = useNavigate();
  const [semanaBase, setSemanaBase] = useState(() => segundaFeiraDaSemana(new Date()));
  const [reunioes, setReunioes] = useState<ReuniaoAgenda[]>([]);
  const [carregando, setCarregando] = useState(true);

  const diasDaSemana = useMemo(() => Array.from({ length: 7 }, (_, indice) => adicionarDias(semanaBase, indice)), [semanaBase]);

  useEffect(() => {
    setCarregando(true);
    const dataInicio = chaveDia(semanaBase);
    const dataFim = chaveDia(adicionarDias(semanaBase, 6));
    api
      .get<ReuniaoAgenda[]>(`/reunioes?data_inicio=${dataInicio}&data_fim=${dataFim}`)
      .then(setReunioes)
      .catch(() => setReunioes([]))
      .finally(() => setCarregando(false));
  }, [semanaBase]);

  const reunioesPorDia = useMemo(() => {
    const mapa = new Map<string, ReuniaoAgenda[]>();
    for (const reuniao of reunioes) {
      const chave = chaveDia(new Date(reuniao.horario_confirmado ?? reuniao.data_hora));
      const lista = mapa.get(chave) ?? [];
      lista.push(reuniao);
      mapa.set(chave, lista);
    }
    for (const lista of mapa.values()) {
      lista.sort(
        (a, b) => new Date(a.horario_confirmado ?? a.data_hora).getTime() - new Date(b.horario_confirmado ?? b.data_hora).getTime(),
      );
    }
    return mapa;
  }, [reunioes]);

  const hojeChave = chaveDia(new Date());

  return (
    <div className="p-5.5">
      <div className="mb-5 flex items-end justify-between">
        <div>
          <div className="font-head text-xl font-bold">Agenda</div>
          <div className="mt-0.5 text-[11px] text-muted">Visão semanal dos seus compromissos</div>
        </div>
        <div className="flex items-center gap-2">
          <Button size="sm" onClick={() => setSemanaBase(adicionarDias(semanaBase, -7))}>
            ← Semana anterior
          </Button>
          <Button size="sm" onClick={() => setSemanaBase(segundaFeiraDaSemana(new Date()))}>
            Hoje
          </Button>
          <Button size="sm" onClick={() => setSemanaBase(adicionarDias(semanaBase, 7))}>
            Semana seguinte →
          </Button>
        </div>
      </div>

      {carregando ? (
        <div className="text-[12px] text-muted">Carregando agenda...</div>
      ) : (
        <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-7">
          {diasDaSemana.map((dia, indice) => {
            const chave = chaveDia(dia);
            const reunioesDoDia = reunioesPorDia.get(chave) ?? [];
            const ehHoje = chave === hojeChave;
            return (
              <Card key={chave} className={ehHoje ? "border-cyan/50" : undefined}>
                <div className={`mb-2 text-[10px] font-semibold tracking-wide uppercase ${ehHoje ? "text-cyan" : "text-muted"}`}>
                  {DIAS_SEMANA[indice]}
                  <div className="text-[13px] font-bold text-text">
                    {dia.toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" })}
                  </div>
                </div>
                <div className="flex flex-col gap-1.5">
                  {reunioesDoDia.map((reuniao) => (
                    <button
                      key={reuniao.id}
                      type="button"
                      onClick={() => navigate(`/leads/contas/${reuniao.conta_id}`)}
                      className="flex flex-col gap-0.5 rounded-lg border border-border bg-surf2 p-2 text-left transition-colors hover:border-cyan/50"
                    >
                      <div className="flex items-center justify-between gap-1">
                        <span className="text-[11px] font-semibold text-text">
                          {new Date(reuniao.horario_confirmado ?? reuniao.data_hora).toLocaleTimeString("pt-BR", {
                            hour: "2-digit",
                            minute: "2-digit",
                          })}
                        </span>
                        <Badge tone={toneStatus(reuniao.status)}>{reuniao.status}</Badge>
                      </div>
                      <div className="text-[11px] text-text">{reuniao.conta_nome}</div>
                      <div className="text-[10.5px] text-muted">{reuniao.decisor_nome}</div>
                    </button>
                  ))}
                </div>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}
