import { Input } from "@/components/ui/Input";

export interface ItemCampo {
  id: number;
  descricao: string;
}
export interface RespostaCampo {
  id: number;
  texto: string;
}

/** Campos de uma proposta/resposta (Phase E/F): usados pelo comprador ao registrar e pelo fornecedor no portal. */
export function CamposProposta({
  itens,
  respostas,
  valorTotal = itens.length === 0,
}: {
  itens: ItemCampo[];
  respostas: RespostaCampo[];
  /** Sem itens a proposta informa o valor total. */
  valorTotal?: boolean;
}) {
  return (
    <>
      {valorTotal && (
        <Input
          name="valor_total"
          type="number"
          min={0}
          step="0.01"
          placeholder="Valor total"
          className="w-36"
        />
      )}
      {itens.map((i) => (
        <Input
          key={i.id}
          name={`item-${i.id}`}
          type="number"
          min={0}
          step="0.0001"
          placeholder={`Preço unit. ${i.descricao}`}
          className="w-48"
        />
      ))}
      <Input
        name="prazo"
        type="number"
        min={0}
        placeholder="Prazo (dias)"
        className="w-28"
      />
      <Input
        name="pagamento"
        placeholder="Condições de pagamento"
        className="w-48"
      />
      {respostas.map((r) => (
        <Input
          key={r.id}
          name={`req-${r.id}`}
          placeholder={`Resposta: ${r.texto}`}
          className="w-full"
        />
      ))}
    </>
  );
}
