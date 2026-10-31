// Nome com que uma empresa aparece nas listas e seletores: o nome fantasia, quando há, senão a razão social.
export function rotuloDaConta(conta: { nome: string; nome_fantasia: string | null }): string {
  return conta.nome_fantasia || conta.nome;
}
