import { useEffect, useState } from "react";

import { Button } from "@/components/ui/Button";
import { Card, SectionLabel } from "@/components/ui/Card";
import { Input, Select, Textarea } from "@/components/ui/Input";
import { api, mensagemErro } from "@/lib/api";
import { brl, type Configuracao } from "@/lib/mapPerformance";
import { ProntidaoPerformance } from "@/pages/map/performance/ProntidaoPerformance";

/** Configuração versionada do MAP Performance (só gestor): prontidão (vínculo com o CRM, ofertas, contato efetivo),
 * quotas por competência/representante e as políticas (performance, comissão privada e campanhas). Toda mudança exige motivo, cria uma
 * versão nova e fica na auditoria. */
export function ConfiguracaoPerformance() {
  const [config, setConfig] = useState<Configuracao | null>(null);
  const [mensagem, setMensagem] = useState<string | null>(null);
  const [quota, setQuota] = useState({ representante_id: "", competencia: "", valor: "", pipeline_alvo: "", motivo: "" });
  const [politica, setPolitica] = useState({ codigo: "MAP_PERFORMANCE_POLICY", regras: "", motivo: "" });

  const carregar = () =>
    api.get<Configuracao>("/map/performance/configuracao").then((c) => {
      setConfig(c);
      setPolitica((p) => ({ ...p, regras: JSON.stringify(regrasDe(c, p.codigo), null, 2) }));
    }).catch((e) => setMensagem(mensagemErro(e, "Não foi possível carregar a configuração.")));

  useEffect(() => { void carregar(); }, []);

  function regrasDe(c: Configuracao, codigo: string) {
    if (codigo === "MAP_PERFORMANCE_POLICY") return c.performance.regras;
    if (codigo === "PRIVATE_RECURRING_COMMISSION") return c.comissao_privada.regras;
    return c.campanhas.find((x) => x.codigo === codigo)?.regras ?? {};
  }

  async function executar(acao: () => Promise<unknown>, ok: string) {
    try {
      await acao();
      setMensagem(ok);
      await carregar();
    } catch (e) {
      setMensagem(mensagemErro(e, "Não foi possível salvar."));
    }
  }

  if (!config) return <Card className="p-4 text-[12px] text-muted">{mensagem ?? "Carregando…"}</Card>;
  const nomeRep = (id: number | null) => (id == null ? "Padrão (cada representante)" : config.representantes.find((r) => r.id === id)?.nome ?? `#${id}`);

  return (
    <div className="space-y-3">
      {mensagem && <Card className="p-3 text-[12px]">{mensagem}</Card>}
      <ProntidaoPerformance key={JSON.stringify(config.prontidao)} config={config} executar={executar} />
      <Card className="p-4">
        <SectionLabel>Quotas NEW_MRR ativas</SectionLabel>
        <table className="mt-2 w-full text-[11.5px]">
          <thead className="text-[10px] text-muted uppercase">
            <tr><th className="text-left">Competência</th><th className="text-left">Escopo</th><th className="text-right">Quota</th>
              <th className="text-right">Pipeline alvo</th><th className="text-right">Versão</th></tr>
          </thead>
          <tbody>
            {config.quotas.map((q) => (
              <tr key={q.id} className="border-t border-border">
                <td className="py-1">{q.competencia}</td><td>{nomeRep(q.representante_id)}</td>
                <td className="text-right">{brl(q.valor)}</td>
                <td className="text-right">{q.pipeline_alvo ? brl(q.pipeline_alvo) : `${q.multiplo_cobertura ?? 3}x quota`}</td>
                <td className="text-right">v{q.versao}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <div className="mt-3 grid gap-2 md:grid-cols-6">
          <Select label="Escopo" value={quota.representante_id} onChange={(e) => setQuota({ ...quota, representante_id: e.target.value })}>
            <option value="">Padrão</option>
            {config.representantes.map((r) => <option key={r.id} value={r.id}>{r.nome}</option>)}
          </Select>
          <Input type="month" label="Competência" value={quota.competencia} onChange={(e) => setQuota({ ...quota, competencia: e.target.value })} />
          <Input type="number" label="Quota (R$)" value={quota.valor} onChange={(e) => setQuota({ ...quota, valor: e.target.value })} />
          <Input type="number" label="Pipeline alvo (R$)" value={quota.pipeline_alvo} onChange={(e) => setQuota({ ...quota, pipeline_alvo: e.target.value })} />
          <Input label="Motivo" value={quota.motivo} onChange={(e) => setQuota({ ...quota, motivo: e.target.value })} />
          <div className="flex items-end">
            <Button size="sm" onClick={() => executar(() => api.post("/map/performance/quotas", {
              representante_id: quota.representante_id ? Number(quota.representante_id) : null, competencia: quota.competencia,
              valor: Number(quota.valor), pipeline_alvo: quota.pipeline_alvo ? Number(quota.pipeline_alvo) : null, motivo: quota.motivo,
            }), "Quota registrada (nova versão).")}>Salvar quota</Button>
          </div>
        </div>
      </Card>

      <Card className="p-4">
        <SectionLabel>Políticas versionadas</SectionLabel>
        <div className="mt-2 grid gap-2 md:grid-cols-3">
          <Select label="Política" value={politica.codigo}
            onChange={(e) => setPolitica({ ...politica, codigo: e.target.value, regras: JSON.stringify(regrasDe(config, e.target.value), null, 2) })}>
            <option value="MAP_PERFORMANCE_POLICY">Performance (v{config.performance.versao})</option>
            <option value="PRIVATE_RECURRING_COMMISSION">Comissão privada recorrente (v{config.comissao_privada.versao})</option>
            {config.campanhas.map((c) => <option key={c.codigo} value={c.codigo}>Campanha {c.codigo.replace("CAMPAIGN:", "")} (v{c.versao})</option>)}
          </Select>
          <Input label="Motivo" value={politica.motivo} onChange={(e) => setPolitica({ ...politica, motivo: e.target.value })} />
          <div className="flex items-end">
            <Button size="sm" onClick={() => executar(async () => {
              const regras = JSON.parse(politica.regras) as Record<string, unknown>;
              await api.post("/map/performance/politicas", { codigo: politica.codigo, regras, motivo: politica.motivo });
            }, "Política salva (nova versão).")}>Salvar nova versão</Button>
          </div>
        </div>
        <Textarea className="mt-2 font-mono text-[11px]" rows={18} value={politica.regras}
          onChange={(e) => setPolitica({ ...politica, regras: e.target.value })} />
      </Card>
    </div>
  );
}
