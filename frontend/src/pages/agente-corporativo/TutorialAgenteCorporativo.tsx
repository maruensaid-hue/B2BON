import { GuiaPassoAPasso, type PassoGuia } from "@/components/onboarding/GuiaPassoAPasso";

const PASSOS_TUTORIAL_AGENTE_CORPORATIVO: PassoGuia[] = [
  {
    id: "agente-corporativo:modo",
    titulo: "Escolha o modo do agente",
    descricao: "\"Interno\" só pra você testar; \"Assistido\" libera outras empresas conectadas do Shoal pra perguntar.",
  },
  {
    id: "agente-corporativo:testar",
    titulo: "Teste antes de expor",
    descricao: "Simule uma pergunta — a resposta usa só o que você já cadastrou (Ofertas, Perfil, FAQ), nunca inventa.",
  },
  {
    id: "agente-corporativo:pendentes",
    titulo: "Revise antes de responder",
    descricao: "Toda pergunta recebida vem com um rascunho da IA — você edita se precisar e só então aprova ou recusa.",
  },
];

interface TutorialAgenteCorporativoProps {
  open: boolean;
  onClose: () => void;
}

/** Tutorial do módulo Agente Corporativo (raio-X 2026-09-21) — mesmo
 * padrão de `TutorialCrm.tsx`. */
export function TutorialAgenteCorporativo({ open, onClose }: TutorialAgenteCorporativoProps) {
  return (
    <GuiaPassoAPasso
      open={open}
      onClose={onClose}
      passos={PASSOS_TUTORIAL_AGENTE_CORPORATIVO}
      atributoSeletor="data-tutorial-id"
      atributoToggle="data-tutorial-toggle"
    />
  );
}
