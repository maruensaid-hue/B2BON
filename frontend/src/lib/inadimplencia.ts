/** Datas do quadro de inadimplentes e da daily chegam como "AAAA-MM-DD" (data de Brasília calculada no backend): formata sem passar por `Date`, que
 * converteria para o fuso do navegador e poderia mostrar o dia anterior. */
export function formatarData(iso: string | null | undefined): string {
  if (!iso) return "—";
  const [ano, mes, dia] = iso.slice(0, 10).split("-");
  return `${dia}/${mes}/${ano}`;
}

export function formatarMoeda(valor: number | null | undefined): string {
  return valor == null ? "—" : valor.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}
