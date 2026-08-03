import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";

import { api, getToken, limparSessao, setSessao } from "@/lib/api";

export interface Usuario {
  id: number;
  tenant_id: string;
  nome: string;
  email: string;
  papel: string;
  ativo: boolean;
}

interface TokenResponse {
  access_token: string;
  usuario: Usuario;
}

interface AuthContextValue {
  usuario: Usuario | null;
  autenticado: boolean;
  entrar: (email: string, senha: string) => Promise<void>;
  entrarComGoogle: (idToken: string) => Promise<void>;
  sair: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

function lerUsuarioSalvo(): Usuario | null {
  const bruto = localStorage.getItem("b2bon_usuario");
  if (!bruto) return null;
  try {
    return JSON.parse(bruto) as Usuario;
  } catch {
    return null;
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [usuario, setUsuario] = useState<Usuario | null>(lerUsuarioSalvo);

  const entrar = useCallback(async (email: string, senha: string) => {
    const resposta = await api.post<TokenResponse>("/auth/login", { email, senha });
    setSessao(resposta.access_token, resposta.usuario);
    setUsuario(resposta.usuario);
  }, []);

  const entrarComGoogle = useCallback(async (idToken: string) => {
    const resposta = await api.post<TokenResponse>("/auth/google", { id_token: idToken });
    setSessao(resposta.access_token, resposta.usuario);
    setUsuario(resposta.usuario);
  }, []);

  const sair = useCallback(() => {
    limparSessao();
    setUsuario(null);
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({ usuario, autenticado: Boolean(usuario && getToken()), entrar, entrarComGoogle, sair }),
    [usuario, entrar, entrarComGoogle, sair],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth precisa estar dentro de <AuthProvider>");
  return context;
}
