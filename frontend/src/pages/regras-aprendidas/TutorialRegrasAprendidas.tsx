import { GuiaPassoAPasso, type PassoGuia } from "@/components/onboarding/GuiaPassoAPasso";

const PASSOS_TUTORIAL_REGRAS_APRENDIDAS: PassoGuia[] = [
  {
    id: "regras-aprendidas:nova",
    titulo: "Escreva uma regra",
    descricao: "Estilo/conteúdo que a IA deve respeitar (ou evitar) — entra sozinha no prompt da próxima cadência gerada.",
  },
  {
    id: "regras-aprendidas:lista",
    titulo: "Escopo por ICP/Oferta/canal",
    descricao: "Cada regra pode valer pra tudo (\"Todos\"/\"Todas\") ou só pra um ICP, Oferta ou canal específico.",
  },
  {
    id: "regras-aprendidas:sugerir-ia",
    titulo: "IA sugere a partir dos seus próprios ajustes",
    descricao: "Editou ou rejeitou uma mensagem recentemente? Peça pra IA sugerir o texto de uma regra a partir dessa correção.",
  },
  {
    id: "regras-aprendidas:padroes",
    titulo: "Padrões observados",
    descricao: "Correlações reais do seu histórico de negócios (ticket médio, ciclo, motivo de perda) — sempre com o tamanho da amostra.",
  },
];

interface TutorialRegrasAprendidasProps {
  open: boolean;
  onClose: () => void;
}

/** Tutorial do módulo Regras Aprendidas (raio-X 2026-09-21) — mesmo
 * padrão de `TutorialCrm.tsx`. */
export function TutorialRegrasAprendidas({ open, onClose }: TutorialRegrasAprendidasProps) {
  return (
    <GuiaPassoAPasso
      open={open}
      onClose={onClose}
      passos={PASSOS_TUTORIAL_REGRAS_APRENDIDAS}
      atributoSeletor="data-tutorial-id"
      atributoToggle="data-tutorial-toggle"
    />
  );
}
