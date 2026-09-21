import { GuiaPassoAPasso, type PassoGuia } from "@/components/onboarding/GuiaPassoAPasso";

const PASSOS_TUTORIAL_PROSPECCAO: PassoGuia[] = [
  {
    id: "prospeccao:criar-icp",
    titulo: "Crie seu ICP",
    descricao: "Defina segmento, porte, região e CNAEs do cliente ideal — é a base pra gerar listas de contas reais da Receita Federal.",
  },
  {
    id: "prospeccao:origem",
    titulo: "Três formas de trazer contas",
    descricao: "Por ICP (geradas automaticamente), Clientes Cadastrados (avulsos) ou Listas de Prospecção (importadas via planilha).",
  },
  {
    id: "prospeccao:gerar-lista",
    titulo: "Gere a lista de contas",
    descricao: "Com um ICP selecionado, gere contas reais que batem com o perfil, direto da base da Receita Federal.",
  },
  {
    id: "prospeccao:criar-lista",
    titulo: "Importe sua própria lista",
    descricao: "Já tem uma planilha de prospects? Importe aqui, mapeando as colunas pro formato da plataforma.",
  },
  {
    id: "prospeccao:ver-detalhes",
    titulo: "Enriqueça e mapeie decisores",
    descricao: "Abra qualquer conta pra pesquisar o site, mapear decisores e pedir uma sugestão de estratégia de venda com IA.",
  },
];

interface TutorialProspeccaoProps {
  open: boolean;
  onClose: () => void;
}

/** Tutorial do módulo Prospecção (raio-X 2026-09-21) — mesmo padrão de
 * `TutorialCrm.tsx`: coexiste com o tour grande, dispara sozinho na
 * primeira visita (ver `Prospeccao.tsx`). */
export function TutorialProspeccao({ open, onClose }: TutorialProspeccaoProps) {
  return (
    <GuiaPassoAPasso
      open={open}
      onClose={onClose}
      passos={PASSOS_TUTORIAL_PROSPECCAO}
      atributoSeletor="data-tutorial-id"
      atributoToggle="data-tutorial-toggle"
    />
  );
}
