import { Card } from "@/components/ui/Card";

export function AcessoRestrito({
  mensagem = "Esta área é restrita ao Admin da B2B ON (super_admin).",
}: {
  mensagem?: string;
}) {
  return (
    <div className="p-5.5">
      <Card className="flex flex-col items-center py-16 text-center">
        <div className="mb-3 text-4xl opacity-25">🔒</div>
        <div className="text-[12px] text-muted">{mensagem}</div>
      </Card>
    </div>
  );
}
