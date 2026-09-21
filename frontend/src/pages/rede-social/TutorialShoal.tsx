import { GuiaPassoAPasso, type PassoGuia } from "@/components/onboarding/GuiaPassoAPasso";

const PASSOS_TUTORIAL_SHOAL: PassoGuia[] = [
  {
    id: "shoal:perfil",
    titulo: "Complete seu perfil",
    descricao: "Logo, setor, mercados e produtos/serviços — é o que outras empresas veem de você na rede. Solicite verificação pra ganhar o selo.",
  },
  {
    id: "shoal:diretorio",
    titulo: "Encontre outras empresas",
    descricao: "Busque por setor, porte ou mercado, e conecte-se (com aceite mútuo) ou siga sem aceite.",
  },
  {
    id: "shoal:feed",
    titulo: "Publique no feed",
    descricao: "Legenda, carrossel de fotos ou vídeo — visível pra toda a rede de assinantes da B2B ON.",
  },
];

interface TutorialShoalProps {
  open: boolean;
  onClose: () => void;
}

/** Tutorial do módulo Shoal / Rede Social (raio-X 2026-09-21) — mesmo
 * padrão de `TutorialCrm.tsx`. */
export function TutorialShoal({ open, onClose }: TutorialShoalProps) {
  return (
    <GuiaPassoAPasso
      open={open}
      onClose={onClose}
      passos={PASSOS_TUTORIAL_SHOAL}
      atributoSeletor="data-tutorial-id"
      atributoToggle="data-tutorial-toggle"
    />
  );
}
