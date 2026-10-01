import { lazy, Suspense, useEffect, useState, type ReactNode } from "react";

import { Card } from "@/components/ui/Card";
import { AcessoRestrito } from "@/pages/admin/AcessoRestrito";
import { MapContas } from "@/pages/map/MapContas";
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
 * vinculado a um representante vê também o próprio painel de performance. */
export function Map() {
  const { usuario } = useAuth();
  const [representante, setRepresentante] = useState(false);

  useEffect(() => {
    if (usuario && usuario.papel !== "super_admin") {
      api.get<{ pode_ver: boolean }>("/map/performance/acesso").then((a) => setRepresentante(a.pode_ver)).catch(() => setRepresentante(false));
    }
  }, [usuario]);

  if (usuario?.papel === "super_admin") {
    return <Abas abas={[["tenants", "Saúde dos tenants", <MapTenants key="t" />],
      ["performance", "Performance comercial", <PerformanceComercial key="p" gestor />]]} />;
  }
  const abas: [string, string, ReactNode][] = [];
  if (usuario?.recursos_plano.modulo_map) abas.push(["contas", "Saúde das contas", <MapContas key="c" />]);
  if (representante) abas.push(["performance", "Meu desempenho", <PerformanceComercial key="p" gestor={false} />]);
  if (abas.length === 0) {
    return <AcessoRestrito mensagem="O MAP não faz parte do seu plano atual. Fale com o time comercial pra contratar." />;
  }
  return <Abas abas={abas} />;
}
