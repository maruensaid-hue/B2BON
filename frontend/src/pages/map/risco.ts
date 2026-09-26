/** Tom do badge pela classificação de risco do MAP (contas e tenants). */
export function toneClassificacao(classificacao: string): "red" | "amber" | "green" | "muted" {
  if (classificacao === "critico") return "red";
  if (classificacao === "atencao") return "amber";
  if (classificacao === "saudavel") return "green";
  return "muted";
}
