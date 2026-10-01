import { lazy, Suspense, useEffect, useState } from "react";

import { Badge } from "@/components/ui/Badge";
import { Card, SectionLabel } from "@/components/ui/Card";
import { Input, Select } from "@/components/ui/Input";
import { KpiCard } from "@/components/ui/KpiCard";
import { api, mensagemErro } from "@/lib/api";
import {
  brl,
  competenciaAtual,
  pct,
  toneAttainment,
  toneSeveridade,
  vezes,
  type Daily,
  type PainelEquipe,
  type ResumoEquipe,
} from "@/lib/mapPerformance";
import { PainelRepresentante } from "@/pages/map/performance/PainelRepresentante";

const ConfiguracaoPerformance = lazy(() =>
  import("@/pages/map/performance/ConfiguracaoPerformance").then((m) => ({ default: m.ConfiguracaoPerformance })),
);

type Aba = "daily" | "equipe" | "individual" | "configuracao";

function Resumo({ equipe }: { equipe: ResumoEquipe }) {
  return (
    <div className="grid grid-cols-2 gap-2.5 md:grid-cols-3 xl:grid-cols-6">
      <KpiCard label="Quota da equipe" value={brl(equipe.quota)} sub={`${equipe.representantes} representantes`} />
      <KpiCard label="New MRR" value={brl(equipe.realizado_new_mrr)} />
      <KpiCard label="Attainment" value={pct(equipe.attainment)} colorClassName={toneAttainment(equipe.attainment)} sub={`Gap ${brl(equipe.gap)}`} />
      <KpiCard label="Cobertura" value={vezes(equipe.cobertura)} sub={`Pipeline ${brl(equipe.pipeline_mrr)}`} />
      <KpiCard label="Forecast" value={brl(equipe.forecast_new_mrr)} />
      <KpiCard label="Government Pipeline" value={brl(equipe.governo_pipeline_qualificado)} sub="Fora da quota privada" />
    </div>
  );
}

/** Daily Comercial de 15 minutos: só exceções — quem precisa de intervenção, o gap, os negócios que destravam a quota e
 * as próximas ações. */
function DailyComercial({ competencia }: { competencia: string }) {
  const [daily, setDaily] = useState<Daily | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  useEffect(() => {
    setDaily(null);
    api.get<Daily>(`/map/performance/daily?competencia=${competencia}`).then(setDaily)
      .catch((e) => setErro(mensagemErro(e, "Não foi possível carregar o Daily.")));
  }, [competencia]);
  if (erro) return <Card className="p-4 text-[12px] text-red">{erro}</Card>;
  if (!daily) return <Card className="p-4 text-[12px] text-muted">Carregando Daily…</Card>;
  return (
    <div className="space-y-3">
      <Resumo equipe={daily.equipe} />
      <div className="text-[11.5px] text-muted">
        {daily.intervencoes.length} representante(s) precisam de intervenção · {daily.sem_intervencao} sem exceção hoje.
      </div>
      {daily.intervencoes.map((linha) => (
        <Card key={linha.representante.id} className="p-4">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-semibold">{linha.representante.nome}</span>
            <Badge tone="muted">Attainment {pct(linha.attainment)}</Badge>
            <Badge tone="amber">Gap {brl(linha.gap)}</Badge>
            <Badge tone="muted">Cobertura {vezes(linha.cobertura)}</Badge>
          </div>
          <div className="mt-2 space-y-1 text-[11.5px]">
            {linha.alertas.map((a) => (
              <div key={a.codigo}><Badge tone={toneSeveridade(a.severidade)}>{a.severidade}</Badge> {a.mensagem}</div>
            ))}
            {linha.pendencias.map((p) => <div key={p} className="text-amber">Pendência: {p}</div>)}
          </div>
          {linha.negocios_que_destravam.length > 0 && (
            <div className="mt-2 text-[11.5px]">
              <div className="text-[10px] text-muted uppercase">Negócios que destravam a quota</div>
              {linha.negocios_que_destravam.map((n) => (
                <div key={n.id}>{n.nome} · {n.conta} · {brl(n.valor)} ({n.probabilidade}%) — {n.proximo_passo}</div>
              ))}
            </div>
          )}
          {linha.proximas_acoes.length > 0 && (
            <div className="mt-2 text-[11.5px] text-cyan">Próximas ações: {linha.proximas_acoes.join(" · ")}</div>
          )}
        </Card>
      ))}
    </div>
  );
}

function Equipe({ competencia, abrir }: { competencia: string; abrir: (id: number) => void }) {
  const [dados, setDados] = useState<PainelEquipe | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  useEffect(() => {
    setDados(null);
    api.get<PainelEquipe>(`/map/performance/equipe?competencia=${competencia}`).then(setDados)
      .catch((e) => setErro(mensagemErro(e, "Não foi possível carregar a equipe.")));
  }, [competencia]);
  if (erro) return <Card className="p-4 text-[12px] text-red">{erro}</Card>;
  if (!dados) return <Card className="p-4 text-[12px] text-muted">Carregando equipe…</Card>;
  return (
    <div className="space-y-3">
      <Resumo equipe={dados.equipe} />
      <Card className="overflow-x-auto p-4">
        <SectionLabel>Comparação por attainment e indicadores operacionais</SectionLabel>
        <table className="mt-2 w-full min-w-[900px] text-[11.5px]">
          <thead className="text-[10px] text-muted uppercase">
            <tr><th className="text-left">Representante</th><th className="text-right">Attainment</th><th className="text-right">Gap</th>
              <th className="text-right">Cobertura</th><th className="text-right">Forecast</th><th className="text-right">Ticket</th>
              <th>Mix</th><th className="text-right">Contas/sem.</th><th className="text-right">Reuniões/sem.</th>
              <th className="text-right">Oport. atualizadas</th><th className="text-right">Gov (sem.)</th><th className="text-left">Exceções</th></tr>
          </thead>
          <tbody>
            {dados.representantes.map((r) => (
              <tr key={r.representante.id} className="cursor-pointer border-t border-border hover:bg-surf2" onClick={() => abrir(r.representante.id)}>
                <td className="py-1.5">{r.representante.nome}</td>
                <td className={`text-right ${toneAttainment(r.attainment)}`}>{pct(r.attainment)}</td>
                <td className="text-right">{brl(r.gap)}</td>
                <td className="text-right">{vezes(r.cobertura)}</td>
                <td className="text-right">{brl(r.forecast_new_mrr)}</td>
                <td className="text-right">{brl(r.ticket_medio)}</td>
                <td className="text-center">{r.mix_quality ?? "—"}</td>
                <td className="text-right">{pct(r.atividade_semana_pct.contas_trabalhadas)}</td>
                <td className="text-right">{pct(r.atividade_semana_pct.reunioes)}</td>
                <td className="text-right">{pct(r.oportunidades_atualizadas_pct)}</td>
                <td className="text-right">{r.governo_novas_semana}</td>
                <td>{r.alertas.filter((a) => a.severidade === "CRITICAL" || a.severidade === "HIGH").map((a) => (
                  <Badge key={a.codigo} tone={toneSeveridade(a.severidade)}>{a.codigo}</Badge>
                ))}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </div>
  );
}

/** MAP Performance Comercial (D-080). Gestor (super_admin): Daily, equipe, painel de cada representante e configuração.
 * Representante: só o próprio painel. Cada aba carrega os próprios dados só quando aberta. */
export function PerformanceComercial({ gestor }: { gestor: boolean }) {
  const [aba, setAba] = useState<Aba>(gestor ? "daily" : "individual");
  const [competencia, setCompetencia] = useState(competenciaAtual());
  const [representanteId, setRepresentanteId] = useState<number | null>(null);
  const [representantes, setRepresentantes] = useState<{ id: number; nome: string }[]>([]);

  useEffect(() => {
    if (gestor) {
      api.get<{ representantes: { id: number; nome: string }[] }>("/map/performance/configuracao")
        .then((c) => setRepresentantes(c.representantes)).catch(() => setRepresentantes([]));
    }
  }, [gestor]);

  const abas: [Aba, string][] = gestor
    ? [["daily", "Daily Comercial"], ["equipe", "Equipe"], ["individual", "Representante"], ["configuracao", "Configuração"]]
    : [["individual", "Meu desempenho"]];

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-end gap-2">
        {abas.map(([chave, rotulo]) => (
          <button key={chave} type="button" onClick={() => setAba(chave)}
            className={`rounded-lg border px-3 py-1.5 text-[12px] ${aba === chave ? "border-cyan text-cyan" : "border-border text-muted"}`}>
            {rotulo}
          </button>
        ))}
        <div className="ml-auto w-36">
          <Input type="month" label="Competência" value={competencia} onChange={(e) => setCompetencia(e.target.value || competenciaAtual())} />
        </div>
        {gestor && aba === "individual" && (
          <div className="w-52">
            <Select label="Representante" value={representanteId ?? ""} onChange={(e) => setRepresentanteId(Number(e.target.value) || null)}>
              <option value="">Selecione…</option>
              {representantes.map((r) => <option key={r.id} value={r.id}>{r.nome}</option>)}
            </Select>
          </div>
        )}
      </div>
      {aba === "daily" && <DailyComercial competencia={competencia} />}
      {aba === "equipe" && <Equipe competencia={competencia} abrir={(id) => { setRepresentanteId(id); setAba("individual"); }} />}
      {aba === "individual" && (gestor && !representanteId
        ? <Card className="p-4 text-[12px] text-muted">Escolha um representante.</Card>
        : <PainelRepresentante representanteId={representanteId} competencia={competencia} />)}
      {aba === "configuracao" && (
        <Suspense fallback={<Card className="p-4 text-[12px] text-muted">Carregando…</Card>}>
          <ConfiguracaoPerformance />
        </Suspense>
      )}
    </div>
  );
}
