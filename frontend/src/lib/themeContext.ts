import { createContext, useContext } from "react";

/** D-086 — contexto do tema (separado do provider para o fast refresh do React). */
export type ThemeMode = "light" | "dark";

export interface ThemeContextValue {
  tema: ThemeMode;
  alternarTema: () => void;
}

export const ThemeContext = createContext<ThemeContextValue | null>(null);

export function useTheme(): ThemeContextValue {
  const contexto = useContext(ThemeContext);
  if (!contexto) throw new Error("useTheme precisa estar dentro de <ThemeProvider>");
  return contexto;
}
