import type {
  ItemCampo,
  RespostaCampo,
} from "@/components/sourcing/CamposProposta";

/** Lê os campos de `CamposProposta` no formato da API. */
export function lerProposta(
  form: FormData,
  itens: ItemCampo[],
  respostas: RespostaCampo[],
) {
  const texto = (campo: string) => String(form.get(campo) ?? "").trim();
  const numero = (campo: string) =>
    texto(campo) ? Number(form.get(campo)) : null;
  return {
    valor_total: numero("valor_total"),
    prazo_entrega_dias: numero("prazo"),
    condicoes_pagamento: texto("pagamento") || null,
    itens: itens
      .filter((i) => numero(`item-${i.id}`) !== null)
      .map((i) => ({ item_id: i.id, preco_unitario: numero(`item-${i.id}`) })),
    respostas: respostas
      .filter((r) => texto(`req-${r.id}`))
      .map((r) => ({ requisito_id: r.id, resposta: texto(`req-${r.id}`) })),
  };
}
