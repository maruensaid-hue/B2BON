import { Button } from "@/components/ui/Button";
import { cn } from "@/lib/cn";
import { useTheme } from "@/lib/themeContext";

/** D-086 — o ícone mostra a AÇÃO disponível, não o estado: no claro aparece 🌙 (ativar escuro); no escuro, ☀️
 * (ativar claro). É um <button> nativo (Tab, Enter e Espaço funcionam) com rótulo acessível e dica. */
export function ThemeToggle({ className }: { className?: string }) {
  const { tema, alternarTema } = useTheme();
  const rotulo = tema === "dark" ? "Ativar modo claro" : "Ativar modo escuro";
  return (
    <Button
      type="button"
      variant="ghost"
      onClick={alternarTema}
      aria-label={rotulo}
      title={rotulo}
      data-testid="theme-toggle"
      className={cn(
        "h-9 w-9 justify-center rounded-full p-0 text-base leading-none hover:bg-surf2",
        "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-cyan",
        className,
      )}
    >
      <span aria-hidden="true">{tema === "dark" ? "☀️" : "🌙"}</span>
    </Button>
  );
}
