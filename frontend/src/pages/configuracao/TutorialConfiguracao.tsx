import { GuiaPassoAPasso, type PassoGuia } from "@/components/onboarding/GuiaPassoAPasso";

const PASSOS_TUTORIAL_CONFIGURACAO: PassoGuia[] = [
  {
    id: "configuracao:oferta",
    titulo: "Cadastre sua Oferta",
    descricao: "Descrição, diferenciais e provas sociais entram literalmente no texto que a IA usa pra escrever cadências.",
  },
  {
    id: "configuracao:comunicacao",
    titulo: "Tom e restrições",
    descricao: "Defina o tom de voz e o que a IA nunca deve dizer — vale pra toda mensagem gerada, em qualquer canal.",
  },
  {
    id: "configuracao:whatsapp",
    titulo: "Conecte o WhatsApp Business",
    descricao: "Conta própria da Meta — obrigatória pra disparar WhatsApp de cadência/campanha (com template aprovado).",
  },
];

interface TutorialConfiguracaoProps {
  open: boolean;
  onClose: () => void;
}

/** Tutorial do módulo Configuração (raio-X 2026-09-21) — mesmo padrão
 * de `TutorialCrm.tsx`. */
export function TutorialConfiguracao({ open, onClose }: TutorialConfiguracaoProps) {
  return (
    <GuiaPassoAPasso
      open={open}
      onClose={onClose}
      passos={PASSOS_TUTORIAL_CONFIGURACAO}
      atributoSeletor="data-tutorial-id"
      atributoToggle="data-tutorial-toggle"
    />
  );
}
