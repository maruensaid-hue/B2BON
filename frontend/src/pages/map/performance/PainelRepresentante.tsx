import { useEffect, useState } from "react";

import { Badge } from "@/components/ui/Badge";
import { Card, SectionLabel } from "@/components/ui/Card";
import { KpiCard } from "@/components/ui/KpiCard";
import { api, mensagemErro } from "@/lib/api";
import {
  brl,
  pct,
  ROTULOS_ATIVIDADE,
  ROTULOS_ETAPA,
  toneAttainment,
  toneSeveridade,
  vezes,
  type MetaAtividade,
  type PainelIndividual,
} from "@/lib/mapPerformance";

function Metas({ titulo, metas }: { titulo: string; metas: Record<string, MetaAtividade> | null }) {
  if (!metas) return null;
  return (
    <div>
      <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">{titulo}</div>
      <div className="space-y-1.5">
        {Object.entries(metas).map(([campo, meta]) => (
          <div key={campo} className="flex items-center gap-2 text-[11.5px]">
            <span className="w-44 shrink-0 text-muted">{ROTULOS_ATIVIDADE[campo] ?? campo.replaceAll("_", " ")}</span>
            <div className="h-1.5 flex-1 rounded bg-surf2">
              <div className="h-1.5 rounded bg-cyan" style={{ width: `${Math.min((meta.pct ?? 0) * 100, 100)}%` }} />
            </div>
            <span className="w-20 text-right tabular-nums">
              {meta.realizado} / {meta.alvo}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

/** Painel individual: quota → pipeline → atividade → conversão → MRR → comissão → aprendizado. Carregado só quando a
 * aba é aberta (lazy) e com no máximo 20 negócios abertos — nunca o pipeline inteiro. */
export function PainelRepresentante({ representanteId, competencia }: { representanteId: number | null; competencia: string }) {
  const [painel, setPainel] = useState<PainelIndividual | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => {
    const controle = new AbortController();
    const filtro = representanteId ? `&representante_id=${representanteId}` : "";
    setPainel(null);
    api
      .get<PainelIndividual>(`/map/performance/painel?competencia=${competencia}${filtro}`, { signal: controle.signal })
      .then(setPainel)
      .catch((e) => !controle.signal.aborted && setErro(mensagemErro(e, "Não foi possível carregar o painel.")));
    return () => controle.abort();
  }, [representanteId, competencia]);

  if (erro) return <Card className="p-4 text-[12px] text-red">{erro}</Card>;
  if (!painel) return <Card className="p-4 text-[12px] text-muted">Carregando painel…</Card>;
  const funil = painel.funil_mes;

  return (
    <div className="space-y-3">
      {painel.pendencias.length > 0 && (
        <Card className="border-amber/30 p-3 text-[11.5px] text-amber">Pendências: {painel.pendencias.join(" · ")}</Card>
      )}
      <div className="grid grid-cols-2 gap-2.5 md:grid-cols-4 xl:grid-cols-6">
        <KpiCard label="Quota New MRR" value={brl(painel.quota)} sub={painel.competencia} />
        <KpiCard label="Realizado" value={brl(painel.realizado_new_mrr)} sub={`Fechado no CRM: ${brl(painel.fechado_crm_mrr)}`} />
        <KpiCard label="Attainment" value={pct(painel.attainment)} colorClassName={toneAttainment(painel.attainment)} sub={`Gap ${brl(painel.gap)}`} />
        <KpiCard label="Cobertura" value={vezes(painel.pipeline.cobertura)}
          sub={`Pipeline ${brl(painel.pipeline.qualificado_mrr)} · alvo ${brl(painel.pipeline.alvo)}`} />
        <KpiCard label="Forecast" value={brl(painel.forecast_new_mrr)} sub={`Ponderado ${brl(painel.pipeline.ponderado_mrr)}`} />
        <KpiCard label="Ticket médio" value={brl(painel.ticket_medio)} sub={`Baseline ${brl(painel.ticket_medio_baseline)}`} />
      </div>

      {painel.alertas.length > 0 && (
        <Card className="p-4">
          <SectionLabel>MAP Intelligence</SectionLabel>
          <div className="mt-2 space-y-2">
            {painel.alertas.map((a) => (
              <div key={a.codigo} className="flex items-start gap-2 text-[12px]">
                <Badge tone={toneSeveridade(a.severidade)}>{a.severidade}</Badge>
                <div>
                  <div>{a.mensagem}</div>
                  <div className="text-[11px] text-muted">→ {a.acao}</div>
                </div>
              </div>
            ))}
          </div>
        </Card>
      )}

      <div className="grid gap-3 lg:grid-cols-2">
        <Card className="space-y-3 p-4">
          <SectionLabel>Atividade</SectionLabel>
          {painel.atividade.dia ? (
            <>
              <Metas titulo="Hoje" metas={painel.atividade.dia} />
              <Metas titulo="Semana" metas={painel.atividade.semana} />
            </>
          ) : (
            <div className="text-[11.5px] text-muted">Vincule o representante a um usuário do CRM para medir atividade.</div>
          )}
          <div className="text-[10.5px] text-muted">
            Conta trabalhada = ICP validado + persona/contato alvo + ação comercial registrada por uma pessoa. Disparos automáticos não contam.
            {painel.pipeline.atualizadas_pct != null && ` Oportunidades atualizadas: ${pct(painel.pipeline.atualizadas_pct)}.`}
          </div>
        </Card>

        <Card className="p-4">
          <SectionLabel>Funil do mês e conversão</SectionLabel>
          {funil ? (
            <table className="mt-2 w-full text-[11.5px]">
              <thead className="text-[10px] text-muted uppercase">
                <tr><th className="text-left">Etapa</th><th className="text-right">Mês</th><th className="text-right">Baseline</th>
                  <th className="text-right">Observada (90d)</th><th className="text-right">Recomendada</th></tr>
              </thead>
              <tbody>
                {Object.entries(ROTULOS_ETAPA).map(([etapa, rotulo]) => {
                  const t = painel.aprendizado[etapa];
                  return (
                    <tr key={etapa} className="border-t border-border">
                      <td className="py-1">{rotulo}</td>
                      <td className="text-right">{pct(painel.taxas_mes?.[etapa])}</td>
                      <td className="text-right">{pct(t?.baseline)}</td>
                      <td className="text-right">{pct(t?.observada)} <span className="text-muted">({t?.amostra ?? 0})</span></td>
                      <td className="text-right">{pct(t?.recomendada)} {t?.fonte === "OBSERVED" && <Badge tone="green">real</Badge>}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          ) : (
            <div className="mt-2 text-[11.5px] text-muted">Sem vínculo com o CRM.</div>
          )}
          {funil && (
            <div className="mt-2 text-[11px] text-muted">
              {funil.contas_trabalhadas} contas · {funil.contatos_efetivos} contatos · {funil.reunioes} reuniões ·{" "}
              {funil.oportunidades_qualificadas} oportunidades · {funil.propostas} propostas · {funil.fechamentos} fechamentos
            </div>
          )}
        </Card>
      </div>

      <div className="grid gap-3 lg:grid-cols-3">
        <Card className="p-4">
          <SectionLabel>Mix de produto</SectionLabel>
          <div className="mt-2 space-y-1 text-[11.5px]">
            {Object.entries(painel.mix.por_familia).map(([familia, m]) => (
              <div key={familia} className="flex justify-between">
                <span>{familia}</span>
                <span>{brl(m.valor)} · {pct(m.participacao)} <span className="text-muted">(alvo {pct(m.alvo)})</span></span>
              </div>
            ))}
            {Object.keys(painel.mix.por_familia).length === 0 && <div className="text-muted">Sem New MRR no mês.</div>}
          </div>
          <div className="mt-2 text-[11px]">
            Mix Quality: {painel.mix.mix_quality ?? "—"} ({pct(painel.mix.alto_valor_participacao)} em Suite/Bid/Sourcing; mínimo{" "}
            {pct(painel.mix.alto_valor_minimo)}) — indicador, nunca bloqueio.
          </div>
        </Card>
        <Card className="p-4">
          <SectionLabel>Sales velocity</SectionLabel>
          <div className="mt-2 space-y-1 text-[11.5px]">
            {Object.entries(painel.velocidade).map(([classe, v]) => (
              <div key={classe} className="flex justify-between">
                <span>{classe} <span className="text-muted">(~{v.dias_padrao}d; real {v.ciclo_medio_observado ?? "—"}d)</span></span>
                <span>{classe === "STRATEGIC" ? `Gov TCV ${brl(v.pipeline_governo_tcv)}` : `${v.negocios} · ${brl(v.pipeline_mrr)}`}</span>
              </div>
            ))}
          </div>
        </Card>
        <Card className="p-4">
          <SectionLabel>Comissão recorrente ({pct(painel.comissao.taxa)})</SectionLabel>
          <div className="mt-2 space-y-1 text-[11.5px]">
            <div className="flex justify-between"><span>Realizada (paga)</span><span>{brl(painel.comissao.realizada)}</span></div>
            <div className="flex justify-between"><span>A receber</span><span>{brl(painel.comissao.a_receber)}</span></div>
            <div className="flex justify-between"><span>Retida (inadimplência)</span><span>{brl(painel.comissao.retida_inadimplencia)}</span></div>
            <div className="flex justify-between"><span>Aguardando parâmetros</span><span>{painel.comissao.aguardando_parametros}</span></div>
            <div className="text-[10.5px] text-muted">
              Carteira: {painel.carteira.CURRENT ?? 0} adimplentes · {painel.carteira.DELINQUENT ?? 0} inadimplentes ·{" "}
              {painel.carteira.CANCELLED ?? 0} cancelados. Só mensalidade paga gera comissão.
            </div>
          </div>
        </Card>
      </div>

      <div className="grid gap-3 lg:grid-cols-2">
        <Card className="p-4">
          <SectionLabel>Government Pipeline (separado da quota privada)</SectionLabel>
          <div className="mt-2 grid grid-cols-2 gap-1 text-[11.5px]">
            <span>Qualificadas</span><span className="text-right">{painel.governo.qualificadas}</span>
            <span>Pipeline qualificado</span><span className="text-right">{brl(painel.governo.pipeline_qualificado)}</span>
            <span>Licenças</span><span className="text-right">{brl(painel.governo.pipeline_licenca)}</span>
            <span>Subscrição anual</span><span className="text-right">{brl(painel.governo.pipeline_assinatura_anual)}</span>
            <span>Novas na semana</span>
            <span className="text-right">{painel.governo.novas_qualificadas_semana} / {painel.governo.meta_semana}</span>
            <span>Bookings no mês</span><span className="text-right">{brl(painel.governo.bookings_mes)}</span>
          </div>
          {painel.governo.proximos_fechamentos.map((o) => (
            <div key={o.id} className="mt-1 text-[11px] text-muted">{o.fechamento_previsto} · {o.titulo} ({o.estagio})</div>
          ))}
        </Card>
        <Card className="p-4">
          <SectionLabel>Campanhas</SectionLabel>
          {painel.campanhas.length === 0 && <div className="mt-2 text-[11.5px] text-muted">Nenhuma campanha ativa.</div>}
          {painel.campanhas.map((c) => (
            <div key={c.codigo} className="mt-2 text-[11.5px]">
              <div className="font-semibold">{c.nome} <Badge tone="muted">{c.situacao}</Badge></div>
              <div>New MRR {brl(c.new_mrr)} de {brl(c.meta)} ({pct(c.attainment)}) · faixa +{pct(c.faixa_bonus)}</div>
              <div>Base (comissão de novas vendas) {brl(c.base_comissao_novas_vendas)} → bônus {brl(c.bonus)} ({c.status_bonus})</div>
              {!c.elegivel && <div className="text-amber">Inelegível: {c.motivos_inelegibilidade.join("; ")}</div>}
            </div>
          ))}
        </Card>
      </div>

      <Card className="p-4">
        <SectionLabel>Negócios abertos com maior valor ponderado</SectionLabel>
        <table className="mt-2 w-full text-[11.5px]">
          <thead className="text-[10px] text-muted uppercase">
            <tr><th className="text-left">Negócio</th><th className="text-left">Estágio</th><th className="text-right">MRR</th>
              <th className="text-right">Prob.</th><th className="text-left">Velocidade</th><th className="text-right">Sem ação</th>
              <th className="text-left">Próximo passo</th></tr>
          </thead>
          <tbody>
            {painel.negocios_abertos.map((n) => (
              <tr key={n.id} className="border-t border-border">
                <td className="py-1">{n.nome} <span className="text-muted">· {n.conta}</span></td>
                <td>{n.estagio}</td>
                <td className="text-right">{brl(n.valor)}</td>
                <td className="text-right">{n.probabilidade}%</td>
                <td>{n.velocidade} · {n.fechamento_previsto}</td>
                <td className="text-right">{n.dias_sem_acao}d</td>
                <td className="text-muted">{n.proximo_passo ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </div>
  );
}
