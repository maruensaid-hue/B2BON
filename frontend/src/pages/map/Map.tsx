import { lazy, Suspense, useEffect, useState, type ReactNode } from "react";

import { Card } from "@/components/ui/Card";
import { AcessoRestrito } from "@/pages/admin/AcessoRestrito";
import { MapContas } from "@/pages/map/MapContas";
import { MapInadimplentes } from "@/pages/map/MapInadimplentes";
import { NotasDaily } from "@/pages/map/NotasDaily";
import { MapTenants } from "@/pages/map/MapTenants";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";

// MAP Performance Comercial (D-080): só baixa quando a aba é aberta.
const PerformanceComercial = lazy(() =>
  import("@/pages/map/performance/PerformanceComercial").then((m) => ({ default: m.PerformanceComercial })),
);

function Abas({ abas }: { abas: [string, string, ReactNode][] }) {
  const [ativa, setAtiva] = useState(abas[0][0]);
  if (abas.length === 1) return <>{abas[0][2]}</>;
  return (
    <div className="space-y-3">
      <div className="flex gap-2">
        {abas.map(([chave, rotulo]) => (
          <button key={chave} type="button" onClick={() => setAtiva(chave)}
            className={`rounded-lg border px-3 py-1.5 text-[12px] ${ativa === chave ? "border-cyan text-cyan" : "border-border text-muted"}`}>
            {rotulo}
          </button>
        ))}
      </div>
      <Suspense fallback={<Card className="p-4 text-[12px] text-muted">Carregando…</Card>}>
        {abas.find(([chave]) => chave === ativa)?.[2]}
      </Suspense>
    </div>
  );
}

/** O MAP é para todo mundo, mas o que cada papel vê é diferente:
 * super_admin monitora os TENANTS assinantes da B2B ON (MapTenants,
 * cross-tenant, ferramenta interna — não é o módulo MAP vendido ao
 * cliente, por isso não passa pelo guard de `modulo_map` abaixo) e a
 * Performance Comercial dos representantes (D-080);
 * user/admin monitoram as CONTAS (clientes/prospects) do próprio tenant
 * (MapContas, escopada por vendedor — esse sim é o MAP avulso). Um usuário
 * vinculado a um representante vê também o próprio painel de performance.
 * Pedido do PO (18/11/2026): aba "Clientes inadimplentes" (parcelas dos
 * negócios ganhos + licenças B2B ON vencidas, cada uma para quem pode ver)
 * e, para o gestor, as anotações da daily em destaque no topo. */
export function Map() {
  const { usuario } = useAuth();
  const [representante, setRepresentante] = useState(false);
  const [acesso, setAcesso] = useState<{ licencas: boolean; notas_daily: boolean }>({ licencas: false, notas_daily: false });

  useEffect(() => {
    if (usuario && usuario.papel !== "super_admin") {
      api.get<{ pode_ver: boolean }>("/map/performance/acesso").then((a) => setRepresentante(a.pode_ver)).catch(() => setRepresentante(false));
    }
    if (usuario) {
      api.get<{ licencas: boolean; notas_daily: boolean }>("/map/inadimplencia/acesso").then(setAcesso).catch(() => undefined);
    }
  }, [usuario]);

  const temMap = usuario?.papel === "super_admin" || !!usuario?.recursos_plano.modulo_map;
  const abaInadimplentes: [string, string, ReactNode] | null = temMap || acesso.licencas
    ? ["inadimplentes", "Clientes inadimplentes", <MapInadimplentes key="i" verParcelas={temMap} verLicencas={acesso.licencas} />]
    : null;

  const abas: [string, string, ReactNode][] = [];
  if (usuario?.papel === "super_admin") {
    abas.push(["tenants", "Saúde dos tenants", <MapTenants key="t" />]);
    if (abaInadimplentes) abas.push(abaInadimplentes);
    abas.push(["performance", "Performance comercial", <PerformanceComercial key="p" gestor />]);
  } else {
    if (usuario?.recursos_plano.modulo_map) abas.push(["contas", "Saúde das contas", <MapContas key="c" />]);
    if (abaInadimplentes) abas.push(abaInadimplentes);
    if (representante) abas.push(["performance", "Meu desempenho", <PerformanceComercial key="p" gestor={false} />]);
  }
  if (abas.length === 0) {
    return <AcessoRestrito mensagem="O MAP não faz parte do seu plano atual. Fale com o time comercial pra contratar." />;
  }
  return (
    <div className="space-y-3">
      {acesso.notas_daily && (
        <div className="px-5.5 pt-4">
          <NotasDaily />
        </div>
      )}
      <Abas abas={abas} />
    </div>
  );
}
