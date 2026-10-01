/** Commission Engine (D-074, D-075): tipos do `/comissoes/*`. */

/** Um tributo do Tax Profile (D-075). Valor null = ainda não informado. */
export interface ComponenteTributo {
  tributo: string;
  base: string;
  rotulo?: string | null;
  aliquota?: number | null;
  presuncao?: number | null;
  limite_periodo?: number | null;
  periodo?: string | null;
  aliquota_teste?: number | null;
  aliquota_caixa_efetiva?: number | null;
  compensado?: boolean;
  dispensado?: boolean;
  status_conformidade?: string | null;
}

export interface PerfilTributario {
  id: number;
  regime: string;
  vigente_de: string;
  vigente_ate: string | null;
  tipo_receita: string;
  municipio: string | null;
  codigo_servico: string | null;
  componentes: ComponenteTributo[];
  fonte: string | null;
  observacoes: string | null;
  pendencias: string[];
}

export interface CotacaoCambio {
  id: number;
  moeda_base: string;
  moeda_cotacao: string;
  taxa: number;
  fonte: string;
  vigente_em: string;
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
  cotacoes_cambio: CotacaoCambio[];
  cotacao_vigente: CotacaoCambio | null;
  tributos: string[];
  bases_tributo: string[];
  categorias_infra: string[];
  metodos_infra: Record<string, string>;
  tipos_receita: string[];
  politica_margem: { versao: number; regras: { deduzir_custo_ia: boolean } };
  pendentes: string[];
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
  total: LinhaWaterfall & {
    impostos_por_tributo: Record<string, number>;
    aguardando_por_parametro: Record<string, number>;
  };
}

/** "PIS 0,65%" / "IRPJ 15% × presunção 32%" / "CBS teste 0,9% (fora da carga)" — "a informar" quando falta valor. */
export function descreverTributo(c: ComponenteTributo): string {
  const p = (v: number | null | undefined) =>
    v === null || v === undefined
      ? "a informar"
      : pct(Math.round(v * 1e6) / 1e4);
  if (c.base === "TESTE_REFORMA")
    return `${c.tributo} teste ${p(c.aliquota_teste)} (${
      c.compensado || c.dispensado
        ? "compensado/dispensado"
        : c.aliquota_caixa_efetiva !== null &&
            c.aliquota_caixa_efetiva !== undefined
          ? `caixa ${p(c.aliquota_caixa_efetiva)}`
          : "fora da carga"
    }${c.status_conformidade ? `, ${c.status_conformidade}` : ""})`;
  if (c.base === "PRESUNCAO")
    return `${c.tributo} ${p(c.aliquota)} × presunção ${p(c.presuncao)}`;
  if (c.base === "PRESUNCAO_EXCEDENTE")
    return `${c.tributo} ${p(c.aliquota)} sobre base presumida acima de ${c.limite_periodo ?? "a informar"}/${c.periodo ?? "período"}`;
  return `${c.rotulo ?? c.tributo} ${p(c.aliquota)}`;
}

export const pct = (valor: number | null | undefined) =>
  valor === null || valor === undefined
    ? "—"
    : `${valor.toLocaleString("pt-BR")}%`;
