import { Button } from "@/components/ui/Button";

/** Botões das próximas etapas que o workflow permite (a tela não fixa estados). */
export function ProximosStatus({
  proximos,
  rotulos,
  ocupado,
  aoEscolher,
}: {
  proximos: string[];
  rotulos: Record<string, string>;
  ocupado: boolean;
  aoEscolher: (status: string) => void;
}) {
  if (proximos.length === 0) return null;
  return (
    <div className="mt-2 flex flex-wrap gap-2">
      {proximos.map((status) => (
        <Button
          key={status}
          size="sm"
          variant="ghost"
          disabled={ocupado}
          onClick={() => aoEscolher(status)}
        >
          {rotulos[status] ?? status}
        </Button>
      ))}
    </div>
  );
}
