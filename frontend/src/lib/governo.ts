/** B2B ON Government (D-072): contrato como o backend devolve (`/assinatura`, `/governo/*`). */

export interface PoolCreditos {
  annual_credit_pool: number;
  credits_consumed: number;
  credits_remaining: number;
  valid_from: string;
  valid_until: string | null;
  credit_source: string;
  status: string;
  subscription_id: number;
  tenant_id: string;
}

export interface PeriodoGoverno {
  id: number;
  numero: number;
  renovacao_numero: number;
  inicio: string;
  fim: string;
  data_renovacao: string;
  valor_assinatura: number;
  valor_reajuste: number;
  status: string;
  status_renovacao: string;
  creditos: PoolCreditos | null;
}

export interface ComponenteGoverno {
  id: number;
  tipo: string;
  descricao: string | null;
  valor: number;
  recorrente: boolean;
  booking_em: string;
  cancelado: boolean;
  recebido: number;
  comissionavel?: boolean;
  taxa_comissao?: number | null;
}

export interface ContratoGoverno {
  id: number;
  tenant_id: string;
  plano_id: number;
  modelo_cobranca: string;
  referencia_contrato: string;
  entidade_governamental: string;
  status: string;
  assinado_em: string;
  valores: {
    licenca: number;
    implantacao: number;
    assinatura_anual: number;
    contratacao_inicial: number;
    creditos_ia_anuais: number;
  };
  periodos: PeriodoGoverno[];
  componentes: ComponenteGoverno[];
  representante_id?: number | null;
}

export const ROTULO_COMPONENTE: Record<string, string> = {
  LICENSE: "Licença institucional",
  IMPLEMENTATION: "Implantação",
  INITIAL_ANNUAL_SUBSCRIPTION: "Subscrição anual inicial",
  RENEWAL_ANNUAL_SUBSCRIPTION: "Renovação da subscrição",
  ADDITIONAL_SERVICES: "Serviços adicionais",
  ADDITIONAL_AI_CREDITS: "AI Credits adicionais",
};

export const ROTULO_MODELO: Record<string, string> = {
  GOVERNMENT_LICENSE_PLUS_ANNUAL_SUBSCRIPTION: "Licença + subscrição anual",
  GOVERNMENT_ANNUAL_SUBSCRIPTION_ONLY: "Somente subscrição anual",
};

export const data = (valor: string | null) =>
  valor ? new Date(valor).toLocaleDateString("pt-BR") : "—";
