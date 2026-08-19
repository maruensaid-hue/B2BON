import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";

import { api, getTemLicencaAtiva, getToken, limparSessao, setSessao } from "@/lib/api";

export interface Usuario {
  id: number;
  tenant_id: string;
  nome: string;
  email: string;
  papel: string;
  ativo: boolean;
  /** distribuidor | revendedor | cliente — raio-X: hierarquia de distribuidores. */
  tenant_tipo: string;
}

interface TokenResponse {
  access_token: string;
  usuario: Usuario;
  tem_licenca_ativa: boolean;
  checkout_url: string | null;
}

interface DadosRegistroVitrine {
  codigo_convite: string;
  razao_social: string;
  cnpj?: string;
  nome_admin: string;
  email_admin: string;
  senha_admin: string;
  aceite_termos: boolean;
  plano_id: number;
}

interface DadosRegistroConvite {
  codigo_convite: string;
  nome: string;
  email: string;
  senha: string;
  aceite_termos: boolean;
}

interface AuthContextValue {
  usuario: Usuario | null;
  autenticado: boolean;
  temLicencaAtiva: boolean;
  entrar: (email: string, senha: string) => Promise<void>;
  entrarComGoogle: (idToken: string) => Promise<void>;
  registrarVitrine: (dados: DadosRegistroVitrine) => Promise<string | null>;
  registrarComConvite: (dados: DadosRegistroConvite) => Promise<void>;
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
  const [temLicencaAtiva, setTemLicencaAtiva] = useState<boolean>(getTemLicencaAtiva);

  const entrar = useCallback(async (email: string, senha: string) => {
    const resposta = await api.post<TokenResponse>("/auth/login", { email, senha });
    setSessao(resposta.access_token, resposta.usuario, resposta.tem_licenca_ativa);
    setUsuario(resposta.usuario);
    setTemLicencaAtiva(resposta.tem_licenca_ativa);
  }, []);

  const entrarComGoogle = useCallback(async (idToken: string) => {
    const resposta = await api.post<TokenResponse>("/auth/google", { id_token: idToken });
    setSessao(resposta.access_token, resposta.usuario, resposta.tem_licenca_ativa);
    setUsuario(resposta.usuario);
    setTemLicencaAtiva(resposta.tem_licenca_ativa);
  }, []);

  const registrarVitrine = useCallback(async (dados: DadosRegistroVitrine) => {
    const resposta = await api.post<TokenResponse>("/auth/registrar-vitrine", dados);
    setSessao(resposta.access_token, resposta.usuario, resposta.tem_licenca_ativa);
    setUsuario(resposta.usuario);
    setTemLicencaAtiva(resposta.tem_licenca_ativa);
    return resposta.checkout_url;
  }, []);

  const registrarComConvite = useCallback(async (dados: DadosRegistroConvite) => {
    const resposta = await api.post<TokenResponse>("/auth/registrar", dados);
    setSessao(resposta.access_token, resposta.usuario, resposta.tem_licenca_ativa);
    setUsuario(resposta.usuario);
    setTemLicencaAtiva(resposta.tem_licenca_ativa);
  }, []);

  const sair = useCallback(() => {
    limparSessao();
    setUsuario(null);
    setTemLicencaAtiva(true);
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({
      usuario,
      autenticado: Boolean(usuario && getToken()),
      temLicencaAtiva,
      entrar,
      entrarComGoogle,
      registrarVitrine,
      registrarComConvite,
      sair,
    }),
    [usuario, temLicencaAtiva, entrar, entrarComGoogle, registrarVitrine, registrarComConvite, sair],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth precisa estar dentro de <AuthProvider>");
  return context;
}
