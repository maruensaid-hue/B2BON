/** Tipos e rótulos compartilhados do Bid Intelligence (Fase 9). */

export interface Licitacao {
  id: number;
  titulo: string;
  orgao_nome: string | null;
  modalidade: string;
  fonte: string;
  fonte_url: string | null;
  prazo_proposta: string | null;
  valor_estimado: number | null;
  status: string;
}

export const MODALIDADES: Record<string, string> = {
  PUBLIC_TENDER: "Licitação pública",
  RFP: "RFP",
  RFI: "RFI",
  RFQ: "RFQ",
  EOI: "Manifestação de interesse",
  DIRECT_AWARD: "Contratação direta",
  PRICE_REGISTRATION: "Registro de preços",
  FRAMEWORK_AGREEMENT: "Acordo-quadro",
  PRIVATE_RFP: "RFP privada",
  PRIVATE_RFI: "RFI privada",
  PRIVATE_RFQ: "RFQ privada (cotação)",
  PRIVATE_TENDER: "Concorrência privada",
};

/** Rótulos dos estados do workflow (os estados em si vêm do servidor). */
export const ROTULO_STATUS: Record<string, string> = {
  IDENTIFICADA: "Identificada",
  EM_ANALISE: "Em análise",
  GO: "GO",
  NO_GO: "NO GO",
  PROPOSTA_ENVIADA: "Proposta enviada",
  EM_NEGOCIACAO: "Em negociação",
  GANHA: "Ganha",
  PERDIDA: "Perdida",
  CANCELADA: "Cancelada",
};
