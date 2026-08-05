import { MapContas } from "@/pages/map/MapContas";
import { MapTenants } from "@/pages/map/MapTenants";
import { useAuth } from "@/lib/auth";

/** O MAP é para todo mundo, mas o que cada papel vê é diferente:
 * super_admin monitora os TENANTS assinantes da B2B ON (MapTenants,
 * cross-tenant); user/admin monitoram as CONTAS (clientes/prospects)
 * do próprio tenant (MapContas, escopada por vendedor). */
export function Map() {
  const { usuario } = useAuth();

  if (usuario?.papel === "super_admin") {
    return <MapTenants />;
  }
  return <MapContas />;
}
