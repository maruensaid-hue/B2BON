/** Commission Engine (D-074): tipos do `/comissoes/*`. */

export interface PerfilTributario {
  id: number;
  regime: string;
  vigente_de: string;
  vigente_ate: string | null;
  tipo_receita: string;
  municipio: string | null;
  componentes: { nome: string; aliquota: number }[];
  aliquota_efetiva: number;
  fonte: string | null;
}

export interface ModeloCustoInfra {
  id: number;
  nome: string;
  vigente_de: string;
  vigente_ate: string | null;
  metodo: string;
  componentes: Record<string, unknown>[];
  fonte: string | null;
}

export interface Parametros {
  perfis_tributarios: PerfilTributario[];
  modelos_custo_infra: ModeloCustoInfra[];
  modelo_vigente_id: number | null;
  componentes_infra: string[];
  tipos_receita: string[];
  politica_governo: {
    versao: number;
    regras: {
      gatilho: string;
      componentes: Record<
        string,
        { comissionavel: boolean; taxa: number | null }
      >;
    };
  };
  politica_privada: string;
}

export interface LinhaWaterfall {
  chave: string | number | null;
  receita_bruta: number;
  impostos: number;
  infraestrutura: number;
  margem_comissionavel_liquida: number;
  comissao: number;
  margem_cyberfort_apos_comissao: number;
  percentuais: Record<string, number | null>;
  aguardando_parametros: number;
}

export interface Waterfall {
  agrupar: string;
  linhas: LinhaWaterfall[];
  total: LinhaWaterfall;
}

export const pct = (valor: number | null | undefined) =>
  valor === null || valor === undefined
    ? "—"
    : `${valor.toLocaleString("pt-BR")}%`;
