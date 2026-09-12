import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";

import { api, getTemLicencaAtiva, getToken, limparSessao, setSessao, setTemLicencaAtiva as persistirTemLicencaAtiva } from "@/lib/api";

/** Gancho de upgrade além de volume (raio-X 2026-09-09) — usada pra
 * mostrar o cadeado direto na UI, sem esperar um 403. A checagem de
 * verdade sempre acontece de novo no backend em cada rota. */
export interface RecursosPlano {
  ab_teste_cadencia: boolean;
  auto_aprovacao: boolean;
  webhook_relatorio: boolean;
  api_parceiros: boolean;
  subtenants: boolean;
  registro_oportunidade: boolean;
  retencao_dias_relatorio: number | null;
}

export interface Usuario {
  id: number;
  tenant_id: string;
  nome: string;
  email: string;
  papel: string;
  ativo: boolean;
  /** distribuidor | revendedor | cliente — raio-X: hierarquia de distribuidores. */
  tenant_tipo: string;
  recursos_plano: RecursosPlano;
}

interface TokenResponse {
  access_token: string;
  usuario: Usuario;
  tem_licenca_ativa: boolean;
  checkout_url: string | null;
  /** True só no primeiro login/cadastro de verdade — dispara o tour
   * guiado de onboarding uma única vez (raio-X 2026-09-01). */
  primeiro_login: boolean;
}

interface DadosRegistroVitrine {
  codigo_convite: string;
  razao_social: string;
  cnpj?: string;
  nome_admin: string;
  email_admin: string;
  senha_admin: string;
  aceite_termos: boolean;
  /** Ausente/null em convite gratuito — o servidor decide o plano "Teste" sozinho. */
  plano_id?: number;
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
  /** True uma única vez, logo após o primeiro login/cadastro — consumido
   * pelo AppShell (abre o tour) via `consumirPrimeiroLoginPendente`. Não
   * reaparece num F5 no meio da sessão. */
  primeiroLoginPendente: boolean;
  consumirPrimeiroLoginPendente: () => void;
  /** Autoatendimento "já paguei" (raio-X 2026-09-09) — reativa
   * `temLicencaAtiva` na hora, sem exigir logout/login, pra desbloquear a
   * navegação assim que o back confirma a autodeclaração. */
  declararPagamento: () => Promise<void>;
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
  const [primeiroLoginPendente, setPrimeiroLoginPendente] = useState(false);

  const entrar = useCallback(async (email: string, senha: string) => {
    const resposta = await api.post<TokenResponse>("/auth/login", { email, senha });
    setSessao(resposta.access_token, resposta.usuario, resposta.tem_licenca_ativa);
    setUsuario(resposta.usuario);
    setTemLicencaAtiva(resposta.tem_licenca_ativa);
    setPrimeiroLoginPendente(resposta.primeiro_login);
  }, []);

  const entrarComGoogle = useCallback(async (idToken: string) => {
    const resposta = await api.post<TokenResponse>("/auth/google", { id_token: idToken });
    setSessao(resposta.access_token, resposta.usuario, resposta.tem_licenca_ativa);
    setUsuario(resposta.usuario);
    setTemLicencaAtiva(resposta.tem_licenca_ativa);
    setPrimeiroLoginPendente(resposta.primeiro_login);
  }, []);

  const registrarVitrine = useCallback(async (dados: DadosRegistroVitrine) => {
    const resposta = await api.post<TokenResponse>("/auth/registrar-vitrine", dados);
    setSessao(resposta.access_token, resposta.usuario, resposta.tem_licenca_ativa);
    setUsuario(resposta.usuario);
    setTemLicencaAtiva(resposta.tem_licenca_ativa);
    setPrimeiroLoginPendente(resposta.primeiro_login);
    return resposta.checkout_url;
  }, []);

  const registrarComConvite = useCallback(async (dados: DadosRegistroConvite) => {
    const resposta = await api.post<TokenResponse>("/auth/registrar", dados);
    setSessao(resposta.access_token, resposta.usuario, resposta.tem_licenca_ativa);
    setUsuario(resposta.usuario);
    setTemLicencaAtiva(resposta.tem_licenca_ativa);
    setPrimeiroLoginPendente(resposta.primeiro_login);
  }, []);

  const sair = useCallback(() => {
    limparSessao();
    setUsuario(null);
    setTemLicencaAtiva(true);
    setPrimeiroLoginPendente(false);
  }, []);

  const consumirPrimeiroLoginPendente = useCallback(() => {
    setPrimeiroLoginPendente(false);
  }, []);

  const declararPagamento = useCallback(async () => {
    await api.post<{ status: string }>("/auth/declarar-pagamento");
    persistirTemLicencaAtiva(true);
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
      primeiroLoginPendente,
      consumirPrimeiroLoginPendente,
      declararPagamento,
    }),
    [
      usuario,
      temLicencaAtiva,
      entrar,
      entrarComGoogle,
      registrarVitrine,
      registrarComConvite,
      sair,
      primeiroLoginPendente,
      consumirPrimeiroLoginPendente,
      declararPagamento,
    ],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth precisa estar dentro de <AuthProvider>");
  return context;
}
