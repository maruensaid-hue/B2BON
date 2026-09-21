import { GuiaPassoAPasso, type PassoGuia } from "@/components/onboarding/GuiaPassoAPasso";

const PASSOS_TUTORIAL_LEADS_CONTATOS: PassoGuia[] = [
  {
    id: "leads-contatos:novo",
    titulo: "Cadastre um contato direto",
    descricao: "Associe a uma empresa já cadastrada, sem precisar passar por um ICP.",
  },
  {
    id: "leads-contatos:lista",
    titulo: "Seus contatos",
    descricao: "Todos os decisores de leads que você cadastrou direto, com empresa, e-mail e telefone.",
  },
];

interface TutorialLeadsContatosProps {
  open: boolean;
  onClose: () => void;
}

/** Tutorial do módulo Leads — Contatos (raio-X 2026-09-21) — mesmo
 * padrão de `TutorialCrm.tsx`. */
export function TutorialLeadsContatos({ open, onClose }: TutorialLeadsContatosProps) {
  return (
    <GuiaPassoAPasso
      open={open}
      onClose={onClose}
      passos={PASSOS_TUTORIAL_LEADS_CONTATOS}
      atributoSeletor="data-tutorial-id"
      atributoToggle="data-tutorial-toggle"
    />
  );
}
