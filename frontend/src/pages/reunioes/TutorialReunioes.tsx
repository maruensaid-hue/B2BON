import { GuiaPassoAPasso, type PassoGuia } from "@/components/onboarding/GuiaPassoAPasso";

const PASSOS_TUTORIAL_REUNIOES: PassoGuia[] = [
  {
    id: "reunioes:filtro",
    titulo: "Filtre por status",
    descricao: "Horários propostos, agendada, realizada, no-show — acompanhe o ciclo completo de cada reunião marcada.",
  },
  {
    id: "reunioes:lista",
    titulo: "Confirme, marque o resultado",
    descricao: "Confirme um horário proposto, marque uma reunião agendada como realizada ou no-show, e confirme se foi qualificada.",
  },
  {
    id: "reunioes:dossie",
    titulo: "Dossiê automático",
    descricao: "Depois de realizada, veja o dossiê gerado automaticamente — dores levantadas, score e a próxima ação recomendada.",
  },
];

interface TutorialReunioesProps {
  open: boolean;
  onClose: () => void;
}

/** Tutorial do módulo Reuniões (raio-X 2026-09-21) — mesmo padrão de
 * `TutorialCrm.tsx`. */
export function TutorialReunioes({ open, onClose }: TutorialReunioesProps) {
  return (
    <GuiaPassoAPasso
      open={open}
      onClose={onClose}
      passos={PASSOS_TUTORIAL_REUNIOES}
      atributoSeletor="data-tutorial-id"
      atributoToggle="data-tutorial-toggle"
    />
  );
}
