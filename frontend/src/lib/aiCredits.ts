import { api } from "@/lib/api";

/** Pacote de AI Credits como a API devolve (catálogo versionado). Preço
 * nunca fica fixo no frontend. */
export interface Pacote {
  codigo: string;
  nome: string;
  versao: number;
  creditos: number | null;
  preco: number | null;
  moeda: string;
  status: "ATIVO" | "CONTACT_SALES" | "INATIVO";
  validade_meses: number | null;
  preco_efetivo_por_1000: number | null;
}

export interface Franquia {
  produto: string;
  creditos: number | null;
  status: string;
  faixa: string | null;
  observacao: string | null;
}

export interface Estimativa {
  creditos_estimados: number;
  requer_confirmacao: boolean;
  mensagem: string;
  disponivel?: number;
}

export const brl = (valor: number) =>
  valor.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });

export const creditos = (valor: number) =>
  `${Math.round(valor).toLocaleString("pt-BR")} créditos`;

/** Operação cara: busca a estimativa e pede confirmação antes de executar.
 * Devolve `null` se o usuário desistir; senão, o valor do parâmetro
 * `confirmar` a enviar. */
export async function confirmarConsumo(
  caminhoEstimativa: string,
): Promise<boolean | null> {
  const estimativa = await api.get<Estimativa>(caminhoEstimativa);
  if (!estimativa.requer_confirmacao) return false;
  return window.confirm(`${estimativa.mensagem}\n\nDeseja continuar?`)
    ? true
    : null;
}
