import { GuiaPassoAPasso, type PassoGuia } from "@/components/onboarding/GuiaPassoAPasso";

const PASSOS_TUTORIAL_LEADS_EMPRESAS: PassoGuia[] = [
  {
    id: "leads-empresas:nova",
    titulo: "Cadastre um lead direto",
    descricao: "Cliente por indicação, evento ou contato pessoal — sem precisar passar por um ICP.",
  },
  {
    id: "leads-empresas:lista",
    titulo: "Sua lista de leads",
    descricao: "Clique numa empresa pra ver detalhes, cadastrar contatos e criar uma oportunidade no CRM.",
  },
];

interface TutorialLeadsEmpresasProps {
  open: boolean;
  onClose: () => void;
}

/** Tutorial do módulo Leads — Empresas (raio-X 2026-09-21) — mesmo
 * padrão de `TutorialCrm.tsx`. */
export function TutorialLeadsEmpresas({ open, onClose }: TutorialLeadsEmpresasProps) {
  return (
    <GuiaPassoAPasso
      open={open}
      onClose={onClose}
      passos={PASSOS_TUTORIAL_LEADS_EMPRESAS}
      atributoSeletor="data-tutorial-id"
      atributoToggle="data-tutorial-toggle"
    />
  );
}
