import { AcessoRestrito } from "@/pages/admin/AcessoRestrito";
import { MapContas } from "@/pages/map/MapContas";
import { MapTenants } from "@/pages/map/MapTenants";
import { useAuth } from "@/lib/auth";

/** O MAP é para todo mundo, mas o que cada papel vê é diferente:
 * super_admin monitora os TENANTS assinantes da B2B ON (MapTenants,
 * cross-tenant, ferramenta interna — não é o módulo MAP vendido ao
 * cliente, por isso não passa pelo guard de `modulo_map` abaixo);
 * user/admin monitoram as CONTAS (clientes/prospects) do próprio tenant
 * (MapContas, escopada por vendedor — esse sim é o MAP avulso). */
export function Map() {
  const { usuario } = useAuth();

  if (usuario?.papel === "super_admin") {
    return <MapTenants />;
  }
  if (!usuario?.recursos_plano.modulo_map) {
    return <AcessoRestrito mensagem="O MAP não faz parte do seu plano atual. Fale com o time comercial pra contratar." />;
  }
  return <MapContas />;
}
