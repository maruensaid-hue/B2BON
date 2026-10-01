import type { PassoGuia } from "@/components/onboarding/GuiaPassoAPasso";

export const PASSOS_TUTORIAL_SOURCING: PassoGuia[] = [
  {
    id: "sourcing:novo",
    titulo: "Novo processo de compra",
    descricao:
      "Escolha o tipo — RFP, RFQ (cotação), RFI, concorrência privada, qualificação — e descreva a necessidade. Os dados do comprador não vão para a rede nem para o lado vendedor.",
  },
  {
    id: "sourcing:processos",
    titulo: "Processos",
    descricao:
      "No workspace de cada processo: requisitos e critérios com peso, itens, descoberta de fornecedores (seu cadastro e a rede), convites, comparação de propostas, shortlist, negociação, aprovação e adjudicação. Nenhum vencedor é escolhido automaticamente.",
  },
  {
    id: "sourcing:processos",
    titulo: "Fornecedor convidado",
    descricao:
      "Empresas da rede respondem em Convites de compra; quem não tem conta recebe um link secreto (Supplier Guest), que não ocupa usuário. Cada fornecedor vê só o próprio convite.",
  },
  {
    id: "sourcing:processos",
    titulo: "Inteligência do processo",
    descricao:
      "A IA sugere requisitos a partir da especificação e ajuda na avaliação citando o que o fornecedor escreveu. Consome AI Credits (estimativa antes de confirmar), documento RESTRICTED nunca vai para a IA e nada vale sem a sua confirmação.",
  },
];
