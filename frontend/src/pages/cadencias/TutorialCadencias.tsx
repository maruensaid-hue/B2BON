import { GuiaPassoAPasso, type PassoGuia } from "@/components/onboarding/GuiaPassoAPasso";

const PASSOS_TUTORIAL_CADENCIAS: PassoGuia[] = [
  {
    id: "cadencias:nova",
    titulo: "Crie uma cadência",
    descricao: "Escolha ICP, Oferta e canais — a IA escreve os toques da sequência sozinha, sempre sob sua aprovação depois.",
  },
  {
    id: "cadencias:toques",
    titulo: "A sequência de toques",
    descricao: "Cada linha é um toque (e-mail, WhatsApp, LinkedIn) com seu intervalo de dias — edite, reordene ou remova antes de ativar.",
  },
  {
    id: "cadencias:ativar",
    titulo: "Ativar pra disparar",
    descricao: "Depois de aprovar as mensagens em Aprovações, ative a cadência aqui pra ela começar a disparar de verdade.",
  },
];

interface TutorialCadenciasProps {
  open: boolean;
  onClose: () => void;
}

/** Tutorial do módulo Cadências (raio-X 2026-09-21) — mesmo padrão de
 * `TutorialCrm.tsx`. */
export function TutorialCadencias({ open, onClose }: TutorialCadenciasProps) {
  return (
    <GuiaPassoAPasso
      open={open}
      onClose={onClose}
      passos={PASSOS_TUTORIAL_CADENCIAS}
      atributoSeletor="data-tutorial-id"
      atributoToggle="data-tutorial-toggle"
    />
  );
}
