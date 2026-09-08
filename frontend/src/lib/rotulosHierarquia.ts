import { useEffect, useState } from "react";

import { api } from "@/lib/api";

export interface RotuloTipoTenant {
  tipo: string;
  rotulo: string;
}

/** Mesmo default do backend (`rotulo_hierarquia_service`) — usado como
 * estado inicial enquanto o fetch não volta, e como fallback se ele falhar. */
export const ROTULOS_PADRAO: Record<string, string> = {
  distribuidor: "Master",
  revendedor: "Vendedor",
  cliente: "Cliente",
};

/** `tenant.tipo` é sempre um dos 3 valores internos fixos
 * (distribuidor/revendedor/cliente — regra de negócio em
 * `tenant_service.TIPOS_TENANT_VALIDOS`, nunca muda); o texto exibido pra
 * cada um é configurável em Admin → Tenants, por isso todo lugar que
 * mostra o tipo de um tenant passa por aqui em vez de exibir o valor
 * interno direto. */
export function rotuloTipo(rotulos: Record<string, string>, tipo: string): string {
  return rotulos[tipo] ?? tipo;
}

/** Hook de leitura pra telas que só exibem os rótulos (não editam) — quem
 * precisa editar (Admin → Tenants) gerencia o próprio estado pra atualizar
 * a tela na hora, sem esperar um novo fetch. */
export function useRotulosHierarquia(): Record<string, string> {
  const [rotulos, setRotulos] = useState<Record<string, string>>(ROTULOS_PADRAO);

  useEffect(() => {
    api
      .get<RotuloTipoTenant[]>("/rotulos-hierarquia")
      .then((lista) => {
        const mapa: Record<string, string> = {};
        for (const item of lista) mapa[item.tipo] = item.rotulo;
        setRotulos(mapa);
      })
      .catch(() => {
        // Mantém os padrões se a busca falhar — nunca trava a tela por isso.
      });
  }, []);

  return rotulos;
}
