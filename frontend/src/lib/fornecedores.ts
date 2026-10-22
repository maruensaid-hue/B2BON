/** A plataforma não expõe fornecedores: nomes de provedores e de modelos que cheguem de dados internos (custos, margens) são trocados por rótulos genéricos
 * antes de aparecer na tela. O que não for um fornecedor conhecido passa como veio. */
export function ocultarFornecedor(valor: string | null | undefined): string {
  if (valor === null || valor === undefined) return "—";
  const v = valor.toLowerCase();
  if (v.includes("anthropic")) return "Provedor de IA";
  if (v.includes("claude")) {
    if (v.includes("opus")) return "Modelo de IA avançado";
    if (v.includes("haiku")) return "Modelo de IA rápido";
    if (v.includes("sonnet")) return "Modelo de IA padrão";
    return "Modelo de IA";
  }
  if (v.includes("sendgrid")) return "Serviço de e-mail";
  if (v.includes("mercado") && v.includes("pago")) return "Processador de pagamento";
  if (v.includes("lusha")) return "Provedor de contatos";
  if (v.includes("brasilapi") || v.includes("brasil api")) return "Dados cadastrais públicos";
  return valor;
}
