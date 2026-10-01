/** Catálogo comercial (Fase 14) — tipos e rótulos do `GET /catalogo`.
 * O backend é a fonte: o que não está DISPONIVEL nunca vira botão de compra. */

export type Disponibilidade =
  | "DISPONIVEL"
  | "INCLUIDO"
  | "GRATUITO"
  | "BETA"
  | "SOB_CONSULTA"
  | "EM_DEFINICAO";

export interface ProdutoCatalogo {
  id: string;
  nome: string;
  descricao: string;
  modulo?: string | null;
  incluido_com?: string | null;
  recursos?: string[];
  disponibilidade: Disponibilidade;
  status_preco:
    | "DEFINIDO"
    | "A_PARTIR_DE"
    | "INCLUIDO"
    | "GRATUITO"
    | "PENDING_DEFINITION";
  planos?: string[];
  conectores?: {
    sistema: string;
    nome: string;
    disponibilidade: Disponibilidade;
    liberado_para_conexao: boolean;
  }[];
}

export interface PlanoCatalogo {
  id: number;
  nome: string;
  categoria: string;
  preco_mensal: number;
  /** Phase I: FIXED vai para o checkout; STARTING_AT é "a partir de" (venda assistida). */
  tipo_preco: "FIXED" | "STARTING_AT";
  self_service: boolean;
  ai_credits_mensais: number;
  max_usuarios: number | null;
  modulos: string[];
  limites: Record<string, number | null>;
  recursos: Record<string, boolean>;
}

/** Linha comercial (Phase I, D-059): produto como é vendido na página. */
export interface LinhaComercial {
  id: string;
  nome: string;
  descricao: string;
  lado: "SELL" | "BUY";
  produtos: string[];
  planos: PlanoCatalogo[];
  /** O que o PO ainda não definiu: a página mostra "a definir", nunca um número. */
  pendencias: string[];
  status_preco: "DEFINIDO" | "PENDING_DEFINITION";
}

/** B2B ON Government (D-072): licença + implantação + subscrição anual, sem valor mensal. */
export interface OfertaGoverno {
  id: number;
  nome: string;
  segmento: "GOVERNMENT";
  modelo_cobranca: string;
  periodicidade: "ANUAL";
  recomendado: boolean;
  modulos: string[];
  licenca: number;
  implantacao: number;
  assinatura_anual: number;
  contratacao_inicial: number;
  creditos_ia_anuais: number | null;
  /** Valor null = "conforme contrato". */
  entitlements: Record<string, number | string | boolean | null>;
}

export interface CatalogoGoverno {
  id: string;
  nome: string;
  descricao: string;
  composicao: string;
  renovacao: string;
  adaptacao: string;
  so_assinatura: string;
  modelos: string[];
  planos: OfertaGoverno[];
}

export interface Catalogo {
  moeda: string;
  produtos: ProdutoCatalogo[];
  planos: PlanoCatalogo[];
  linhas: LinhaComercial[];
  governo: CatalogoGoverno;
}

export const ROTULO_DISPONIBILIDADE: Record<Disponibilidade, string> = {
  DISPONIVEL: "Disponível",
  INCLUIDO: "Incluído",
  GRATUITO: "Gratuito",
  BETA: "Beta (liberação sob pedido)",
  SOB_CONSULTA: "Sob consulta · preço em definição",
  EM_DEFINICAO: "Em breve · preço em definição",
};

export const TOM_DISPONIBILIDADE: Record<
  Disponibilidade,
  "green" | "cyan" | "amber" | "muted"
> = {
  DISPONIVEL: "green",
  INCLUIDO: "cyan",
  GRATUITO: "green",
  BETA: "amber",
  SOB_CONSULTA: "amber",
  EM_DEFINICAO: "muted",
};

export const ROTULO_LIMITE: Record<string, string> = {
  franquia_contas_mes: "Contas ativadas por mês (PREDATOR)",
  cadencias_mes: "Cadências por mês",
  campanhas_mes: "Campanhas por mês",
  enriquecimento_site_semanal: "Enriquecimentos de site por semana",
  enriquecimento_contatos_semanal: "Enriquecimentos de contato por semana",
};

export const ROTULO_RECURSO: Record<string, string> = {
  ab_teste_cadencia: "Teste A/B de cadência",
  auto_aprovacao: "Autoaprovação de mensagens",
  webhook_relatorio: "Webhook de relatórios",
  api_parceiros: "API de parceiros",
  subtenants: "Subcontas",
  registro_oportunidade: "Registro de oportunidade",
};

/** `null` = sem teto; `0` = não incluído. */
export function formatarLimite(valor: number | null | undefined): string {
  if (valor === null || valor === undefined) return "Ilimitado";
  if (valor === 0) return "—";
  return valor.toLocaleString("pt-BR");
}

/** Rótulos dos entitlements Government (D-075). Os valores vêm sempre do catálogo central (`GET /catalogo`). */
const ROTULOS_ENTITLEMENT: Record<string, string> = {
  internal_users: "Usuários internos",
  administrative_units: "Unidades administrativas",
  storage_gb: "Armazenamento",
  operational_retention_months: "Retenção operacional",
  crm: "CRM",
  map: "MAP",
  predator: "PREDATOR",
  bid_intelligence: "Bid Intelligence",
  public_procurement: "Public Procurement",
  business_network: "Business Network",
  corporate_brain: "Corporate Brain",
  api_access: "API",
  sso: "SSO",
  support_sla: "Suporte",
  onboarding: "Onboarding",
};

const VALORES_ENTITLEMENT: Record<string, string> = {
  BASIC: "Básico",
  FULL: "Completo",
  OPTIONAL: "Opcional",
  BUSINESS_HOURS_8X5: "8x5 horário comercial",
  PRIORITY_BUSINESS_HOURS_8X5: "8x5 prioritário",
  CRITICAL_BUSINESS_HOURS_8X5: "8x5 crítico",
  STANDARD: "Padrão",
  ADVANCED: "Avançado",
  DEDICATED: "Dedicado",
};

export function linhasEntitlements(
  entitlements: OfertaGoverno["entitlements"],
): [string, string][] {
  return Object.entries(entitlements).map(([chave, valor]) => {
    let texto: string;
    if (valor === null) texto = "Conforme contrato";
    else if (valor === true) texto = "Incluído";
    else if (valor === false) texto = "Não incluído";
    else if (chave === "storage_gb")
      texto =
        Number(valor) >= 1024 ? `${Number(valor) / 1024} TB` : `${valor} GB`;
    else if (chave === "operational_retention_months") texto = `${valor} meses`;
    else texto = VALORES_ENTITLEMENT[String(valor)] ?? String(valor);
    return [ROTULOS_ENTITLEMENT[chave] ?? chave, texto];
  });
}
