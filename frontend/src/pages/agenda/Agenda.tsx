import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Select } from "@/components/ui/Input";
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

type ModoAgenda = "dia" | "semana_util" | "semana" | "mes";

const DIAS_SEMANA = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"];

const OPCOES_MODO: { valor: ModoAgenda; rotulo: string }[] = [
  { valor: "dia", rotulo: "Dia" },
  { valor: "semana_util", rotulo: "Semana útil" },
  { valor: "semana", rotulo: "Semana" },
  { valor: "mes", rotulo: "Mês" },
];

const ROTULO_PASSO: Record<ModoAgenda, string> = {
  dia: "Dia",
  semana_util: "Semana",
  semana: "Semana",
  mes: "Mês",
};

// Classes Tailwind ESTÁTICAS (nunca interpoladas) — o JIT do Tailwind
// precisa da classe literal aparecer no código pra não ser podada.
const COLUNAS_GRID: Record<"dia" | "semana_util" | "semana", string> = {
  dia: "grid-cols-1",
  semana_util: "grid-cols-1 sm:grid-cols-5",
  semana: "grid-cols-1 sm:grid-cols-7",
};

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

/** Rótulo do dia da semana (`DIAS_SEMANA` é Segunda-primeiro) a partir
 * de `Date.getDay()` (0=domingo) — conversão pro índice certo. */
function rotuloDiaSemana(data: Date): string {
  return DIAS_SEMANA[(data.getDay() + 6) % 7];
}

/** Limites (início/fim, inclusive) da grade visível de cada modo — a
 * grade de mês inclui dias de meses vizinhos (esmaecidos na UI) pra
 * sempre fechar semanas completas, padrão comum de calendário mensal. */
function limitesDoModo(modo: ModoAgenda, dataReferencia: Date): { inicio: Date; fim: Date } {
  if (modo === "dia") {
    const dia = new Date(dataReferencia);
    dia.setHours(0, 0, 0, 0);
    return { inicio: dia, fim: dia };
  }
  if (modo === "semana_util") {
    const segunda = segundaFeiraDaSemana(dataReferencia);
    return { inicio: segunda, fim: adicionarDias(segunda, 4) };
  }
  if (modo === "semana") {
    const segunda = segundaFeiraDaSemana(dataReferencia);
    return { inicio: segunda, fim: adicionarDias(segunda, 6) };
  }
  const primeiroDoMes = new Date(dataReferencia.getFullYear(), dataReferencia.getMonth(), 1);
  const ultimoDoMes = new Date(dataReferencia.getFullYear(), dataReferencia.getMonth() + 1, 0);
  return {
    inicio: segundaFeiraDaSemana(primeiroDoMes),
    fim: adicionarDias(segundaFeiraDaSemana(ultimoDoMes), 6),
  };
}

function diasEntre(inicio: Date, fim: Date): Date[] {
  const dias: Date[] = [];
  let atual = inicio;
  while (atual.getTime() <= fim.getTime()) {
    dias.push(atual);
    atual = adicionarDias(atual, 1);
  }
  return dias;
}

function agruparEmSemanas(dias: Date[]): Date[][] {
  const semanas: Date[][] = [];
  for (let indice = 0; indice < dias.length; indice += 7) {
    semanas.push(dias.slice(indice, indice + 7));
  }
  return semanas;
}

/** Agenda (raio-X 2026-09-22, modos de visualização 2026-09-24) —
 * calendário de compromissos (Reuniao), item de menu novo e separado
 * da página "Reuniões" (que continua sendo a lista/gestão de status).
 * Busca por intervalo de data a cada troca de período — GET
 * /reunioes?data_inicio=&data_fim= (filtro já existente no backend,
 * aceita qualquer intervalo — nenhuma mudança de backend precisou ser
 * feita pra suportar os 4 modos), nunca carrega o histórico inteiro do
 * tenant de uma vez. */
export function Agenda() {
  const navigate = useNavigate();
  const [modo, setModo] = useState<ModoAgenda>("semana");
  const [dataReferencia, setDataReferencia] = useState(() => new Date());
  const [reunioes, setReunioes] = useState<ReuniaoAgenda[]>([]);
  const [carregando, setCarregando] = useState(true);

  const { inicio, fim } = useMemo(() => limitesDoModo(modo, dataReferencia), [modo, dataReferencia]);
  const diasVisiveis = useMemo(() => diasEntre(inicio, fim), [inicio, fim]);

  useEffect(() => {
    setCarregando(true);
    api
      .get<ReuniaoAgenda[]>(`/reunioes?data_inicio=${chaveDia(inicio)}&data_fim=${chaveDia(fim)}`)
      .then(setReunioes)
      .catch(() => setReunioes([]))
      .finally(() => setCarregando(false));
  }, [inicio, fim]);

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

  function navegar(direcao: 1 | -1) {
    if (modo === "mes") {
      setDataReferencia((atual) => new Date(atual.getFullYear(), atual.getMonth() + direcao, 1));
      return;
    }
    const passo = modo === "dia" ? 1 : 7;
    setDataReferencia((atual) => adicionarDias(atual, passo * direcao));
  }

  function abrirDia(dia: Date) {
    setModo("dia");
    setDataReferencia(dia);
  }

  return (
    <div className="p-5.5">
      <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
        <div>
          <div className="font-head text-xl font-bold">Agenda</div>
          <div className="mt-0.5 text-[11px] text-muted">Visão de compromissos</div>
        </div>
        <div className="flex items-center gap-2">
          <Select value={modo} onChange={(event) => setModo(event.target.value as ModoAgenda)} className="w-36">
            {OPCOES_MODO.map((opcao) => (
              <option key={opcao.valor} value={opcao.valor}>
                {opcao.rotulo}
              </option>
            ))}
          </Select>
          <Button size="sm" onClick={() => navegar(-1)}>
            ← {ROTULO_PASSO[modo]} anterior
          </Button>
          <Button size="sm" onClick={() => setDataReferencia(new Date())}>
            Hoje
          </Button>
          <Button size="sm" onClick={() => navegar(1)}>
            {ROTULO_PASSO[modo]} seguinte →
          </Button>
        </div>
      </div>

      {carregando ? (
        <div className="text-[12px] text-muted">Carregando agenda...</div>
      ) : modo === "mes" ? (
        <div className="flex flex-col gap-1.5">
          <div className="grid grid-cols-7 gap-1.5">
            {DIAS_SEMANA.map((rotulo) => (
              <div key={rotulo} className="text-center text-[10px] font-semibold tracking-wide text-muted uppercase">
                {rotulo.slice(0, 3)}
              </div>
            ))}
          </div>
          {agruparEmSemanas(diasVisiveis).map((semana) => (
            <div key={chaveDia(semana[0])} className="grid grid-cols-7 gap-1.5">
              {semana.map((dia) => {
                const chave = chaveDia(dia);
                const reunioesDoDia = reunioesPorDia.get(chave) ?? [];
                const ehHoje = chave === hojeChave;
                const foraDoMes = dia.getMonth() !== dataReferencia.getMonth();
                return (
                  <div
                    key={chave}
                    className={`min-h-[84px] rounded-lg border p-1.5 ${
                      ehHoje ? "border-cyan/50 bg-cyan/5" : "border-border"
                    } ${foraDoMes ? "opacity-40" : ""}`}
                  >
                    <button
                      type="button"
                      onClick={() => abrirDia(dia)}
                      className={`text-[11px] font-bold hover:text-cyan ${ehHoje ? "text-cyan" : "text-text"}`}
                    >
                      {dia.getDate()}
                    </button>
                    <div className="mt-1 flex flex-col gap-0.5">
                      {reunioesDoDia.slice(0, 2).map((reuniao) => (
                        <button
                          key={reuniao.id}
                          type="button"
                          onClick={() => navigate(`/leads/contas/${reuniao.conta_id}`)}
                          className="truncate rounded bg-surf2 px-1 py-0.5 text-left text-[9.5px] text-text hover:text-cyan"
                          title={`${reuniao.conta_nome} — ${reuniao.decisor_nome}`}
                        >
                          {new Date(reuniao.horario_confirmado ?? reuniao.data_hora).toLocaleTimeString("pt-BR", {
                            hour: "2-digit",
                            minute: "2-digit",
                          })}{" "}
                          {reuniao.conta_nome}
                        </button>
                      ))}
                      {reunioesDoDia.length > 2 && (
                        <button
                          type="button"
                          onClick={() => abrirDia(dia)}
                          className="text-left text-[9.5px] text-muted hover:text-cyan"
                        >
                          +{reunioesDoDia.length - 2} mais
                        </button>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          ))}
        </div>
      ) : (
        <div className={`grid gap-2.5 ${COLUNAS_GRID[modo]}`}>
          {diasVisiveis.map((dia) => {
            const chave = chaveDia(dia);
            const reunioesDoDia = reunioesPorDia.get(chave) ?? [];
            const ehHoje = chave === hojeChave;
            return (
              <Card key={chave} className={ehHoje ? "border-cyan/50" : undefined}>
                <div className={`mb-2 text-[10px] font-semibold tracking-wide uppercase ${ehHoje ? "text-cyan" : "text-muted"}`}>
                  {rotuloDiaSemana(dia)}
                  <div className="text-[13px] font-bold text-text">
                    {dia.toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" })}
                  </div>
                </div>
                <div className="flex flex-col gap-1.5">
                  {reunioesDoDia.length === 0 && modo === "dia" && (
                    <div className="text-[11px] text-muted">Nenhum compromisso neste dia.</div>
                  )}
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
