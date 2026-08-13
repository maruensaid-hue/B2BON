import clsx, { type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

// clsx sozinho concatena classes sem resolver conflito — duas utilities
// que mexem na mesma propriedade (ex.: "w-full" do componente base +
// "w-32" passado via className no uso) ficam as duas no DOM, e quem
// vence é decidido pela ordem de definição no CSS gerado pelo Tailwind,
// não pela ordem no atributo class (armadilha real: já quebrou o layout
// de campos lado a lado em mais de uma tela). twMerge resolve isso
// mantendo só a última utility em conflito.
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}
