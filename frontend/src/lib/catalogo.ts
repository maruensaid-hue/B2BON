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
  status_preco: "DEFINIDO" | "INCLUIDO" | "GRATUITO" | "PENDING_DEFINITION";
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
  max_usuarios: number | null;
  modulos: string[];
  limites: Record<string, number | null>;
  recursos: Record<string, boolean>;
}

export interface Catalogo {
  moeda: string;
  produtos: ProdutoCatalogo[];
  planos: PlanoCatalogo[];
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
