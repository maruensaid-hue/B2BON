import {
  GuiaPassoAPasso,
  type PassoGuia,
} from "@/components/onboarding/GuiaPassoAPasso";
import type { useTutorialModulo } from "@/components/onboarding/useTutorialModulo";

type EstadoTutorial = ReturnType<typeof useTutorialModulo>;

/** Tutorial de um módulo (`data-tutorial-id`); `BotaoReverTutorial` reabre ao lado do título. */
export function TutorialModulo({
  passos,
  tutorial,
}: {
  passos: PassoGuia[];
  tutorial: EstadoTutorial;
}) {
  return (
    <GuiaPassoAPasso
      open={tutorial.aberto}
      onClose={tutorial.fechar}
      passos={passos}
      atributoSeletor="data-tutorial-id"
      atributoToggle="data-tutorial-toggle"
    />
  );
}

export function BotaoReverTutorial({ tutorial }: { tutorial: EstadoTutorial }) {
  return (
    <button
      type="button"
      onClick={tutorial.abrir}
      disabled={!tutorial.pronto}
      className="text-[11px] text-muted hover:text-cyan disabled:opacity-50"
    >
      🔄 Rever tutorial
    </button>
  );
}
