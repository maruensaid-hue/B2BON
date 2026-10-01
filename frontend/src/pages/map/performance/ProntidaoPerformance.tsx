import { useState } from "react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, SectionLabel } from "@/components/ui/Card";
import { Input, Select } from "@/components/ui/Input";
import { api } from "@/lib/api";
import { ROTULOS_TIPO_ATIVIDADE, type Configuracao, type UsuarioCrm } from "@/lib/mapPerformance";

/** Prontidão do MAP Performance (OI-029): o que falta configurar, num lugar só. O time pode ter qualquer tamanho —
 * representantes entram e saem por Admin → Representantes; aqui só se liga cada um ao CRM, classifica as ofertas e
 * confirma o critério de contato efetivo. Cada salvamento é uma versão nova, com motivo, na auditoria. */
export function ProntidaoPerformance({ config, executar }: {
  config: Configuracao;
  executar: (acao: () => Promise<unknown>, ok: string) => Promise<void>;
}) {
  const p = config.prontidao;
  const [busca, setBusca] = useState("");
  const [candidatos, setCandidatos] = useState<UsuarioCrm[]>([]);
  const [representante, setRepresentante] = useState("");
  const [familias, setFamilias] = useState<Record<string, string>>(
    Object.fromEntries(p.ofertas.map((o) => [String(o.id), o.familia ?? ""])),
  );
  const [tipos, setTipos] = useState<string[]>(p.tipos_contato_efetivo);
  const [motivo, setMotivo] = useState("");

  async function buscar(texto: string) {
    setBusca(texto);
    setCandidatos(texto.trim().length >= 2 ? await api.get<UsuarioCrm[]>(`/map/performance/usuarios-crm?busca=${encodeURIComponent(texto)}`) : []);
  }

  return (
    <Card className="space-y-4 p-4">
      <div className="flex flex-wrap items-center gap-2">
        <SectionLabel>Prontidão</SectionLabel>
        {p.pronto ? <Badge tone="green">Tudo configurado</Badge> : <Badge tone="amber">{p.pendencias.length} pendência(s)</Badge>}
        <span className="text-[11.5px] text-muted">
          {p.representantes_ativos} representante(s) ativo(s) · {p.vinculados} vinculado(s) ao CRM · o número de representantes não é fixo
        </span>
      </div>
      {p.pendencias.length > 0 && <ul className="list-disc pl-5 text-[11.5px] text-amber">{p.pendencias.map((x) => <li key={x}>{x}</li>)}</ul>}
      <Input label="Motivo das alterações (obrigatório)" value={motivo} onChange={(e) => setMotivo(e.target.value)} />

      <div>
        <div className="mb-1 text-[10px] tracking-wide text-muted uppercase">1. Vincular representante ao usuário do CRM</div>
        <div className="grid gap-2 md:grid-cols-3">
          <Select label="Representante" value={representante} onChange={(e) => setRepresentante(e.target.value)}>
            <option value="">Selecione…</option>
            {config.representantes.map((r) => (
              <option key={r.id} value={r.id}>{r.nome}{r.usuario_id ? "" : " (sem vínculo)"}</option>
            ))}
          </Select>
          <Input label="Buscar usuário (nome ou e-mail)" value={busca} onChange={(e) => void buscar(e.target.value)} />
        </div>
        {candidatos.map((u) => (
          <div key={u.id} className="mt-1 flex items-center gap-2 text-[11.5px]">
            <span>{u.nome} · {u.email} <span className="text-muted">({u.tenant_id})</span></span>
            {u.vinculado_a && <Badge tone="muted">vinculado a {u.vinculado_a}</Badge>}
            <Button size="sm" variant="ghost" disabled={!representante || !!u.vinculado_a}
              onClick={() => executar(() => api.put(`/map/performance/representantes/${representante}/usuario`, { usuario_id: u.id }),
                "Representante vinculado.")}>Vincular</Button>
          </div>
        ))}
      </div>

      <div>
        <div className="mb-1 text-[10px] tracking-wide text-muted uppercase">2. Produto de cada oferta do CRM</div>
        {p.ofertas.length === 0 ? (
          <div className="text-[11.5px] text-muted">As ofertas aparecem quando houver representante vinculado ao CRM (cadastre-as em Ofertas).</div>
        ) : (
          <>
            {p.ofertas.map((o) => (
              <div key={o.id} className="mt-1 grid grid-cols-2 items-center gap-2 text-[11.5px] md:grid-cols-4">
                <span className="md:col-span-2">{o.nome} <span className="text-muted">({o.tenant_id})</span></span>
                <Select value={familias[String(o.id)] ?? ""} onChange={(e) => setFamilias({ ...familias, [String(o.id)]: e.target.value })}>
                  <option value="">Não classificada</option>
                  {config.familias.map((f) => <option key={f} value={f}>{f}</option>)}
                </Select>
              </div>
            ))}
            <Button size="sm" className="mt-2" disabled={!motivo} onClick={() => executar(() => api.put("/map/performance/ofertas-familias", {
              familias: Object.fromEntries(Object.entries(familias).map(([id, f]) => [id, f || null])), motivo,
            }), "Ofertas classificadas (nova versão da política).")}>Salvar classificação</Button>
          </>
        )}
      </div>

      <div>
        <div className="mb-1 text-[10px] tracking-wide text-muted uppercase">
          3. O que conta como contato efetivo {p.contato_efetivo_confirmado ? <Badge tone="green">confirmado</Badge> : <Badge tone="amber">provisório</Badge>}
        </div>
        <div className="flex flex-wrap gap-3 text-[12px]">
          {config.tipos_atividade.map((t) => (
            <label key={t} className="flex items-center gap-1">
              <input type="checkbox" checked={tipos.includes(t)}
                onChange={(e) => setTipos(e.target.checked ? [...tipos, t] : tipos.filter((x) => x !== t))} />
              {ROTULOS_TIPO_ATIVIDADE[t] ?? t}
            </label>
          ))}
        </div>
        <Button size="sm" className="mt-2" disabled={!motivo || tipos.length === 0}
          onClick={() => executar(() => api.put("/map/performance/contato-efetivo", { tipos, motivo }), "Critério de contato efetivo confirmado.")}>
          Confirmar critério
        </Button>
      </div>
    </Card>
  );
}
