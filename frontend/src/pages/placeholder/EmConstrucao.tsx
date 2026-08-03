import { Card } from "@/components/ui/Card";

export function EmConstrucao({ titulo }: { titulo: string }) {
  return (
    <div className="p-5.5">
      <div className="mb-5 flex items-end justify-between">
        <div>
          <div className="font-head text-xl font-bold">{titulo}</div>
          <div className="mt-0.5 text-[11px] text-muted">Esta tela chega em uma próxima leva</div>
        </div>
      </div>
      <Card className="flex flex-col items-center justify-center py-16 text-center">
        <div className="mb-3 text-4xl opacity-25">🚧</div>
        <div className="text-[12px] text-muted">
          {titulo} ainda não tem interface própria — o backend já está pronto e será conectado aqui em breve.
        </div>
      </Card>
    </div>
  );
}
