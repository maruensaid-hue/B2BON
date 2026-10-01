import type { PassoGuia } from "@/components/onboarding/GuiaPassoAPasso";

export const PASSOS_TUTORIAL_BIDS: PassoGuia[] = [
  {
    id: "bids:lista",
    titulo: "Licitações em acompanhamento",
    descricao:
      "Editais públicos e RFPs de empresas que a sua empresa acompanha, com o prazo de proposta mais próximo primeiro. Clique numa para abrir o workspace: documentos, requisitos, Go/No-Go, conformidade e proposta.",
  },
  {
    id: "bids:cadastro",
    titulo: "Cadastre uma oportunidade",
    descricao:
      "Título ou número do edital, órgão ou comprador, modalidade (pregão, concorrência, RFP privada...), prazo e valor estimado. Depois envie o edital no workspace: a IA extrai os requisitos com página e trecho, e nada vale sem a sua revisão.",
  },
  {
    id: "bids:prazos",
    titulo: "Prazos que pedem atenção",
    descricao:
      "Propostas e documentos vencendo aparecem aqui antes de virarem problema.",
  },
  {
    id: "bids:cofre",
    titulo: "Cofre de documentos",
    descricao:
      "Certidões, atestados e balanços da sua empresa com validade. Documento vencido ou vencendo aparece na matriz de conformidade de cada licitação.",
  },
  {
    id: "bids:concorrentes",
    titulo: "Concorrentes",
    descricao:
      "Histórico que você registra nas licitações: em quantas disputas encontrou cada concorrente e a sua taxa de vitória contra ele. A recomendação de Go/No-Go é só apoio — a decisão é sua.",
  },
];
