import { GuiaPassoAPasso, type PassoGuia } from "@/components/onboarding/GuiaPassoAPasso";

const PASSOS_TUTORIAL_CAMPANHAS: PassoGuia[] = [
  {
    id: "campanhas:nova",
    titulo: "Crie uma campanha",
    descricao: "Disparo em massa por e-mail/WhatsApp, sem personalização por IA — separado do fluxo de Cadência.",
  },
  {
    id: "campanhas:destinatarios",
    titulo: "Adicione destinatários",
    descricao: "Adicione contatos de contas selecionadas ou cole uma lista pronta — os dois jeitos alimentam a mesma campanha.",
  },
  {
    id: "campanhas:pronta",
    titulo: "Marque como pronta",
    descricao: "Depois de revisar o conteúdo e os destinatários, marque a campanha como pronta pra ela poder ser enviada.",
  },
];

interface TutorialCampanhasProps {
  open: boolean;
  onClose: () => void;
}

/** Tutorial do módulo Campanhas (raio-X 2026-09-21) — mesmo padrão de
 * `TutorialCrm.tsx`. */
export function TutorialCampanhas({ open, onClose }: TutorialCampanhasProps) {
  return (
    <GuiaPassoAPasso
      open={open}
      onClose={onClose}
      passos={PASSOS_TUTORIAL_CAMPANHAS}
      atributoSeletor="data-tutorial-id"
      atributoToggle="data-tutorial-toggle"
    />
  );
}
