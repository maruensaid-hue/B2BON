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
  limite_mensal?: number | null;
  situacao?: string | null;
  acrescimo_presuncao?: {
    percentual: number;
    limite_anual: number;
    periodo?: string;
  } | null;
}

export interface PerfilTributario {
  id: number;
  regime: string;
  vigente_de: string;
  vigente_ate: string | null;
  tipo_receita: string;
  municipio: string | null;
  item_lista_servico: string | null;
  codigo_servico: string | null;
  versao_legal: string | null;
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

/** Componente do Infrastructure Cost Pool (D-076): fornecedor/plano, custos no ciclo e na moeda informados. */
export interface ComponenteInfra {
  id: number;
  fornecedor: string;
  servico: string;
  categoria: string;
  plano: string | null;
  plano_referencia: string | null;
  ciclo_cobranca: string;
  moeda: string;
  custo_contratado: number | null;
  custo_referencia: number | null;
  custo_real: number | null;
  capacidade_contratada: number | null;
  uso_atual: number | null;
  unidade_uso: string | null;
  politica_custo: string;
  metodo_alocacao: string;
  contabilizacao: string;
  vigente_de: string;
  vigente_ate: string | null;
  observacoes: string | null;
  modelo_preco: string;
  status_arquitetura: string;
  provisionado_para_comissao: boolean;
  funcao_arquitetural: string | null;
  url_fonte: string | null;
  tipo_fonte: string;
  verificado_em: string | null;
  proxima_revisao_em: string | null;
  atributos: Record<string, unknown> | null;
}

export interface EnvelopeCapacidade {
  id: number;
  horas_computo_provisionadas: number | null;
  armazenamento_gb_provisionado: number | null;
  custo_mensal_estimado: number | null;
  moeda: string;
  benchmark_only: boolean;
}

export interface LinhaFornecedor {
  id: number;
  fornecedor: string;
  servico: string;
  categoria: string;
  plano_atual: string | null;
  plano_referencia: string | null;
  moeda: string;
  custo_contratado: number | null;
  custo_real: number | null;
  custo_provisionado_mensal_brl: number | null;
  custo_real_mensal_brl: number | null;
  contabilizacao: string;
  capacidade: number | null;
  uso: number | null;
  unidade_uso: string | null;
  utilizacao: number | null;
  status: string | null;
  custo_por_tenant: number | null;
  custo_por_unidade_ponderada: number | null;
  custo_sobre_receita: number | null;
  participacao_pool: number | null;
  no_pool_comissao: boolean;
  status_arquitetura: string;
  modelo_preco: string;
  tipo_fonte: string;
  url_fonte: string | null;
  verificado_em: string | null;
  proxima_revisao_em: string | null;
  revisao_vencida: boolean;
  envelope: EnvelopeCapacidade | null;
  projecao: {
    utilizacao_projetada: Record<string, number>;
    esgotamento_estimado: string | null;
  };
}

export interface AlertaCapacidade {
  id: number;
  componente_id: number;
  nivel: string;
  utilizacao: number;
  mensagem: string;
  status: string;
}

export interface PoliticaInfra {
  pesos: Record<string, number>;
  limiares: Record<string, number>;
  custo_comissao: string;
}

export interface Infraestrutura {
  componentes: ComponenteInfra[];
  categorias: string[];
  ciclos: string[];
  modelos_preco: string[];
  status_arquitetura: string[];
  tipos_fonte: string[];
  politica: PoliticaInfra;
  economia: {
    competencia: string;
    componentes: LinhaFornecedor[];
    alertas_abertos: AlertaCapacidade[];
    resumo: {
      pool_provisionado_mensal: number;
      pool_real_mensal: number | null;
      por_pool: Record<string, number>;
      alocado_tenants_mensal: number;
      capacidade_nao_alocada_mensal: number;
      reserva_mensal: number | null;
      unidades_ponderadas: number;
      tenants_alocados: number;
      planos_sem_peso: string[];
      receita_recorrente_mensal: number;
      custo_sobre_receita: number | null;
      dependencia_maior_fornecedor: {
        fornecedor: string;
        participacao: number;
      } | null;
    };
    projecao: {
      horizonte_dias: number;
      custo_infra_projetado_mensal: number;
      receita_recorrente_projetada_mensal: number;
      custo_sobre_receita_projetado: number | null;
      esgotamentos_ate_180_dias: {
        fornecedor: string;
        servico: string;
        data: string;
      }[];
    };
  };
}

export interface Parametros {
  perfis_tributarios: PerfilTributario[];
  cotacoes_cambio: CotacaoCambio[];
  cotacao_vigente: CotacaoCambio | null;
  tributos: string[];
  bases_tributo: string[];
  situacoes_reforma: string[];
  tipos_receita: string[];
  politica_infraestrutura: { versao: number; regras: PoliticaInfra };
  politica_cambio: Record<string, string>;
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
  infraestrutura_real: number;
  custo_ia: number;
  margem_comissionavel_liquida: number;
  comissao: number;
  margem_cyberfort_apos_comissao: number;
  margem_contribuicao_real: number | null;
  margem_contribuicao_conservadora: number;
  reserva_infraestrutura: number | null;
  infraestrutura_real_incompleta: boolean;
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
    return `${c.tributo} teste ${p(c.aliquota_teste)} (${c.situacao ?? "PENDING_COMPLIANCE_CONFIRMATION"}${
      c.situacao === "PAYABLE" ? "" : ", fora da carga"
    })`;
  if (c.base === "PRESUNCAO")
    return `${c.tributo} ${p(c.aliquota)} × presunção ${p(c.presuncao)}${
      c.acrescimo_presuncao
        ? ` (+${p(c.acrescimo_presuncao.percentual)} na presunção acima de ${brlCurto(c.acrescimo_presuncao.limite_anual)}/ano)`
        : ""
    }`;
  if (c.base === "PRESUNCAO_EXCEDENTE")
    return `${c.tributo} ${p(c.aliquota)} sobre a base do IRPJ acima de ${
      c.limite_mensal !== null && c.limite_mensal !== undefined
        ? `${brlCurto(c.limite_mensal)} × meses`
        : (c.limite_periodo ?? "a informar")
    } (${c.periodo ?? "período"})`;
  return `${c.rotulo ?? c.tributo} ${p(c.aliquota)}`;
}

export const pct = (valor: number | null | undefined) =>
  valor === null || valor === undefined
    ? "—"
    : `${valor.toLocaleString("pt-BR")}%`;

const brlCurto = (valor: number) => `R$ ${valor.toLocaleString("pt-BR")}`;
