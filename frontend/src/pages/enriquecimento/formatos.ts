export function dataExpiracao(valor: string): string {
  // O servidor devolve o instante em UTC sem sufixo; o fim do mês de Brasília cai às 03:00 UTC do dia 1º, então o último dia útil do crédito é o dia anterior.
  const instante = new Date(valor.endsWith("Z") ? valor : `${valor}Z`);
  const ultimo = new Date(instante.getTime() - 1);
  return ultimo.toLocaleDateString("pt-BR", { timeZone: "America/Sao_Paulo" });
}

export function reais(valor: string | null): string {
  return valor === null ? "—" : `R$ ${Number(valor).toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

export function custoCredito(valor: string): string {
  return `R$ ${Number(valor).toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 9 })}`;
}

export function percentual(valor: string): string {
  return `${Number(valor).toLocaleString("pt-BR", { maximumFractionDigits: 1 })}%`;
}

export function dataHora(valor: string): string {
  return new Date(valor.endsWith("Z") ? valor : `${valor}Z`).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" });
}
