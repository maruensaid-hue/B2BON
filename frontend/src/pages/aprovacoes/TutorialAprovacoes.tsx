import { GuiaPassoAPasso, type PassoGuia } from "@/components/onboarding/GuiaPassoAPasso";

const PASSOS_TUTORIAL_APROVACOES: PassoGuia[] = [
  {
    id: "aprovacoes:filtro-status",
    titulo: "Filtre por status",
    descricao: "Pendentes, rejeitadas ou aprovadas — toda mensagem que a IA escreve passa por aqui antes de sair pro contato.",
  },
  {
    id: "aprovacoes:aprovar-item",
    titulo: "Revise e aprove",
    descricao: "Edite o texto se quiser (sua correção vira regra em Regras Aprendidas) e aprove pra ela entrar na fila de envio.",
  },
  {
    id: "aprovacoes:aprovar-todas",
    titulo: "Aprove em lote",
    descricao: "Confiou na cadência inteira? Aprove todas as mensagens visíveis de uma vez.",
  },
];

interface TutorialAprovacoesProps {
  open: boolean;
  onClose: () => void;
}

/** Tutorial do módulo Aprovações (raio-X 2026-09-21) — mesmo padrão de
 * `TutorialCrm.tsx`. */
export function TutorialAprovacoes({ open, onClose }: TutorialAprovacoesProps) {
  return (
    <GuiaPassoAPasso
      open={open}
      onClose={onClose}
      passos={PASSOS_TUTORIAL_APROVACOES}
      atributoSeletor="data-tutorial-id"
      atributoToggle="data-tutorial-toggle"
    />
  );
}
