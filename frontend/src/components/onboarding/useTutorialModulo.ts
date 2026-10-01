import { useEffect, useState } from "react";

import { useAuth } from "@/lib/auth";

/** Estado do tutorial de um módulo: abre sozinho na primeira visita
 * (depois que a tela carregou, `carregado`) e marca como visto ao fechar.
 * Mesma regra dos tutoriais de MAP/CRM, num lugar só para os módulos novos. */
export function useTutorialModulo(modulo: string, carregado: boolean) {
  const { usuario, marcarTutorialModuloVisto } = useAuth();
  const [aberto, setAberto] = useState(false);
  const visto = (usuario?.tutoriais_modulo_vistos ?? []).includes(modulo);

  useEffect(() => {
    if (usuario && carregado && !visto) setAberto(true);
  }, [usuario, carregado, visto]);

  return {
    aberto,
    // Só depois de carregar: aberto antes, o guia pularia os passos cujas
    // seções ainda não estão na tela.
    pronto: carregado,
    abrir: () => setAberto(true),
    fechar: () => {
      setAberto(false);
      if (usuario && !visto) marcarTutorialModuloVisto(modulo);
    },
  };
}
