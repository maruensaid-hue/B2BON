import { GuiaPassoAPasso, type PassoGuia } from "@/components/onboarding/GuiaPassoAPasso";

const PASSOS_TUTORIAL_MAP: PassoGuia[] = [
  {
    id: "map:kpis",
    titulo: "Saúde da carteira em números",
    descricao: "Score médio, contas críticas/em atenção, pipeline em risco, ROI e CS Score — visão geral antes de entrar em cada conta.",
  },
  {
    id: "map:busca",
    titulo: "Busque uma conta específica",
    descricao: "Filtre a lista por nome — combina com os filtros de vendedor/hierarquia ao lado, se você gerenciar mais de uma carteira.",
  },
  {
    id: "map:ranking",
    titulo: "Ranking de saúde",
    descricao: "Clique numa linha pra ver o score de risco, o histórico de interações e gerar um script de resgate com IA pra essa conta.",
  },
];

interface TutorialMapProps {
  open: boolean;
  onClose: () => void;
}

/** Tutorial do módulo MAP (raio-X 2026-09-21) — mesmo padrão de
 * `TutorialCrm.tsx`/`TutorialProspeccao.tsx`. */
export function TutorialMap({ open, onClose }: TutorialMapProps) {
  return (
    <GuiaPassoAPasso
      open={open}
      onClose={onClose}
      passos={PASSOS_TUTORIAL_MAP}
      atributoSeletor="data-tutorial-id"
      atributoToggle="data-tutorial-toggle"
    />
  );
}
