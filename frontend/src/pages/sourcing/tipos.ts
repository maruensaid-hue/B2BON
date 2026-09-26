/** Tipos e rótulos do Strategic Sourcing (Phase E). Estados e próximos passos vêm do workflow no servidor. */

export interface ProcessoSourcing {
  id: number;
  tipo_processo: string;
  titulo: string;
  descricao: string | null;
  status: string;
  workflow: string;
  valor_estimado: number | null;
  moeda: string;
}

export const TIPOS_SOURCING: Record<string, string> = {
  RFP: "RFP",
  RFQ: "RFQ (cotação)",
  RFI: "RFI",
  EOI: "Manifestação de interesse",
  PRIVATE_TENDER: "Concorrência privada",
  VENDOR_QUALIFICATION: "Qualificação de fornecedores",
  STRATEGIC_SOURCING_EVENT: "Evento de sourcing estratégico",
};

export const ROTULO_STATUS_SOURCING: Record<string, string> = {
  RASCUNHO: "Rascunho",
  PUBLICADO: "Publicado",
  RECEBENDO_PROPOSTAS: "Recebendo propostas",
  RECEBENDO_RESPOSTAS: "Recebendo respostas",
  EM_AVALIACAO: "Em avaliação",
  SHORTLIST: "Shortlist",
  EM_NEGOCIACAO: "Em negociação",
  EM_APROVACAO: "Em aprovação",
  ADJUDICADO: "Adjudicado",
  CONTRATADO: "Contratado",
  ENCERRADO: "Encerrado",
  CANCELADO: "Cancelado",
};

export const ROTULO_PARTICIPANTE: Record<string, string> = {
  CONVIDADO: "Convidado",
  RESPONDEU: "Respondeu",
  DECLINOU: "Declinou",
  QUALIFICADO: "Qualificado",
  DESQUALIFICADO: "Desqualificado",
  SHORTLIST: "Shortlist",
  ADJUDICADO: "Adjudicado",
  NAO_SELECIONADO: "Não selecionado",
};

export const CATEGORIAS_SOURCING = [
  "REQUISITO_TECNICO",
  "REQUISITO_COMERCIAL",
  "QUALIFICACAO",
  "SLA",
  "GARANTIA",
  "PRAZO",
  "PERGUNTA",
  "OUTRO",
];
