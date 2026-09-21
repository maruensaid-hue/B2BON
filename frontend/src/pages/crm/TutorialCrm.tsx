import { GuiaPassoAPasso, type PassoGuia } from "@/components/onboarding/GuiaPassoAPasso";

const PASSOS_TUTORIAL_CRM: PassoGuia[] = [
  {
    id: "crm:board",
    titulo: "Seu funil de vendas",
    descricao: "Cada coluna é um estágio do funil. Arraste um card entre colunas pra mover o negócio, ou use o menu dentro do próprio card.",
  },
  {
    id: "crm:mover-estagio",
    titulo: "Mover sem arrastar",
    descricao: "Se preferir não arrastar, esse menu dentro do card também move o negócio direto pro estágio escolhido.",
  },
  {
    id: "crm:novo-negocio",
    titulo: "Criar um negócio novo",
    descricao: "Cadastre uma oportunidade vinculada a uma conta existente ou a um cliente novo, direto por aqui.",
  },
  {
    id: "crm:editar-funil",
    titulo: "Personalizar o funil",
    descricao: "Admin/Super Admin criam, renomeiam, reordenam ou excluem as filas do funil por aqui — o funil é seu, não fixo.",
  },
  {
    id: "crm:importar-exportar",
    titulo: "Importar ou exportar em lote",
    descricao: "Trocando de sistema ou fazendo backup? Importe ou exporte negócios em massa via planilha CSV.",
  },
];

interface TutorialCrmProps {
  open: boolean;
  onClose: () => void;
}

/** Tutorial do módulo CRM (raio-X 2026-09-21) — coexiste com o tour
 * grande de primeiro login; dispara sozinho na primeira visita a este
 * módulo (ver `Kanban.tsx`). Passos reais de interação, não só
 * highlight de menu — por isso usa `data-tutorial-id`, nunca
 * `data-tour-id` (namespace separado do `TourGuiado`). */
export function TutorialCrm({ open, onClose }: TutorialCrmProps) {
  return (
    <GuiaPassoAPasso
      open={open}
      onClose={onClose}
      passos={PASSOS_TUTORIAL_CRM}
      atributoSeletor="data-tutorial-id"
      atributoToggle="data-tutorial-toggle"
    />
  );
}
