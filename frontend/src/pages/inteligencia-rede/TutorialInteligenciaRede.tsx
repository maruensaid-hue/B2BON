import { GuiaPassoAPasso, type PassoGuia } from "@/components/onboarding/GuiaPassoAPasso";

const PASSOS_TUTORIAL_INTELIGENCIA_REDE: PassoGuia[] = [
  {
    id: "inteligencia-rede:fit-icp",
    titulo: "Fit de ICP contra a rede",
    descricao: "Compara seu ICP com o perfil das outras empresas do Shoal — sempre com os motivos do match explicados.",
  },
  {
    id: "inteligencia-rede:atualizar-sinais",
    titulo: "Atualize os sinais",
    descricao: "Sinais de oportunidade não recalculam sozinhos — clique aqui pra cruzar ICP, necessidades declaradas e o grafo comercial de novo.",
  },
  {
    id: "inteligencia-rede:saude-relacionamentos",
    titulo: "Saúde dos relacionamentos",
    descricao: "Última interação + relacionamento comercial declarado, por conexão aceita — mostra quais parcerias estão esfriando.",
  },
];

interface TutorialInteligenciaRedeProps {
  open: boolean;
  onClose: () => void;
}

/** Tutorial do módulo Sinais de Oportunidade (raio-X 2026-09-21) — mesmo
 * padrão de `TutorialCrm.tsx`. */
export function TutorialInteligenciaRede({ open, onClose }: TutorialInteligenciaRedeProps) {
  return (
    <GuiaPassoAPasso
      open={open}
      onClose={onClose}
      passos={PASSOS_TUTORIAL_INTELIGENCIA_REDE}
      atributoSeletor="data-tutorial-id"
      atributoToggle="data-tutorial-toggle"
    />
  );
}
