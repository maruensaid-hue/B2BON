import type { PassoGuia } from "@/components/onboarding/GuiaPassoAPasso";

export const PASSOS_TUTORIAL_COMPRAS: PassoGuia[] = [
  {
    id: "compras:indicadores",
    titulo: "Indicadores do órgão",
    descricao:
      "Visão rápida do plano de contratações, dos processos e dos contratos do órgão comprador.",
  },
  {
    id: "compras:plano",
    titulo: "Plano de contratações",
    descricao:
      "Cadastre o órgão e o plano anual de contratações (PCA) e acompanhe a execução: itens planejados, demandas em risco e o que já virou processo.",
  },
  {
    id: "compras:acoes",
    titulo: "Próximas ações sugeridas",
    descricao:
      "O que o fluxo da Lei 14.133 pede em seguida para cada processo, com o motivo.",
  },
  {
    id: "compras:processos",
    titulo: "Processos",
    descricao:
      "Abra um processo para ver andamento, documentos (ETP, TR, edital), pesquisa de preços e a timeline com auditoria.",
  },
  {
    id: "compras:sinais",
    titulo: "Sinais para revisão",
    descricao:
      "Alertas de risco (aditivos, acréscimos, concentração em fornecedor, prazo de planejamento) com a evidência. São sinais para revisão humana, não acusações; os limites seguem a configuração do órgão.",
  },
];
