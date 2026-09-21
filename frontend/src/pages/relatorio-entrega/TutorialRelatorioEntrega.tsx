import { GuiaPassoAPasso, type PassoGuia } from "@/components/onboarding/GuiaPassoAPasso";

const PASSOS_TUTORIAL_RELATORIO_ENTREGA: PassoGuia[] = [
  {
    id: "relatorio-entrega:saude",
    titulo: "Saúde do canal de e-mail",
    descricao: "Taxa de bounce e spam dos últimos 7 dias — acima do limite, o canal pausa sozinho pra proteger sua reputação.",
  },
  {
    id: "relatorio-entrega:resposta",
    titulo: "Taxa de resposta por canal",
    descricao: "E-mail, WhatsApp e LinkedIn — quanto do que foi enviado gerou resposta.",
  },
  {
    id: "relatorio-entrega:detalhamento",
    titulo: "Detalhamento por destinatário",
    descricao: "Veja cada envio individual; contatos com erro de e-mail podem ser corrigidos ou excluídos direto por aqui.",
  },
];

interface TutorialRelatorioEntregaProps {
  open: boolean;
  onClose: () => void;
}

/** Tutorial do módulo Relatório de Entrega (raio-X 2026-09-21) — mesmo
 * padrão de `TutorialCrm.tsx`. */
export function TutorialRelatorioEntrega({ open, onClose }: TutorialRelatorioEntregaProps) {
  return (
    <GuiaPassoAPasso
      open={open}
      onClose={onClose}
      passos={PASSOS_TUTORIAL_RELATORIO_ENTREGA}
      atributoSeletor="data-tutorial-id"
      atributoToggle="data-tutorial-toggle"
    />
  );
}
