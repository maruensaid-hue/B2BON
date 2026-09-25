import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";

import {
  api,
  atualizarUsuarioSalvo,
  getTemLicencaAtiva,
  getToken,
  limparSessao,
  setSessao,
  setTemLicencaAtiva as persistirTemLicencaAtiva,
} from "@/lib/api";

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
  /** Contratação avulsa por módulo (raio-X 2026-09-24) — um plano de
   * suíte libera os três; um plano avulso só o(s) contratado(s). */
  modulo_map: boolean;
  modulo_predator: boolean;
  modulo_crm: boolean;
  /** Fase 9: Bid Intelligence (B2B ON Public Sector). */
  modulo_bids?: boolean;
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
  aviso_whatsapp_template_confirmado: boolean;
  /** Raio-X 2026-09-15: número pessoal do vendedor, cadastrado em "Meu
   * Perfil" — usado no botão de redirecionamento dos templates de WhatsApp. */
  whatsapp_pessoal: string | null;
  /** Idem — se este usuário tem pelo menos uma `Conta` atribuída
   * (`vendedor_usuario_id`). Liga o aviso proativo de WhatsApp pessoal
   * faltando; computado só no login (não se atualiza sozinho durante a
   * sessão se uma conta nova for atribuída depois). */
  tem_conta_atribuida: boolean;
  /** Redesign Salesforce (raio-X 2026-09-21) — dispensa em definitivo o
   * banner de boas-vindas com atalhos na Dashboard. */
  boas_vindas_banner_dispensado: boolean;
  /** Tutorial por módulo (raio-X 2026-09-21) — chaves de módulo já
   * vistas (ex.: ["crm", "prospeccao"]); `null` = nenhum ainda. */
  tutoriais_modulo_vistos: string[] | null;
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

interface DadosRegistroPublico {
  razao_social: string;
  cnpj?: string;
  nome_admin: string;
  email_admin: string;
  senha_admin: string;
  aceite_termos: boolean;
  plano_id: number;
  representante_id: number;
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
  /** Cadastro público sem convite (raio-X 2026-09-21, página de
   * boas-vindas) — sempre exige um plano pago, nunca o Teste. */
  criarContaPublica: (dados: DadosRegistroPublico) => Promise<string | null>;
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
  /** Dispensa em definitivo o aviso de template do WhatsApp (raio-X
   * 2026-09-14) — some da tela sem precisar de logout/login. */
  confirmarAvisoWhatsappTemplate: () => Promise<void>;
  /** "Meu Perfil" (raio-X 2026-09-15) — salva o WhatsApp pessoal do
   * vendedor, usado no botão de redirecionamento dos templates. */
  atualizarWhatsappPessoal: (whatsappPessoal: string | null) => Promise<void>;
  /** Dispensa em definitivo o banner de boas-vindas da Dashboard (raio-X
   * 2026-09-21) — some da tela sem precisar de logout/login. */
  dispensarBannerBoasVindas: () => Promise<void>;
  /** Tutorial por módulo (raio-X 2026-09-21) — marca um módulo como já
   * visto, idempotente, pra não reabrir sozinho de novo. */
  marcarTutorialModuloVisto: (modulo: string) => Promise<void>;
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

  const criarContaPublica = useCallback(async (dados: DadosRegistroPublico) => {
    const resposta = await api.post<TokenResponse>("/auth/registrar-publico", dados);
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

  const confirmarAvisoWhatsappTemplate = useCallback(async () => {
    await api.post("/configuracao-whatsapp/confirmar-aviso-template");
    setUsuario((atual) => {
      if (!atual) return atual;
      const atualizado = { ...atual, aviso_whatsapp_template_confirmado: true };
      atualizarUsuarioSalvo(atualizado);
      return atualizado;
    });
  }, []);

  const atualizarWhatsappPessoal = useCallback(async (whatsappPessoal: string | null) => {
    await api.put<Usuario>("/auth/whatsapp-pessoal", { whatsapp_pessoal: whatsappPessoal });
    setUsuario((atual) => {
      if (!atual) return atual;
      const atualizado = { ...atual, whatsapp_pessoal: whatsappPessoal };
      atualizarUsuarioSalvo(atualizado);
      return atualizado;
    });
  }, []);

  const dispensarBannerBoasVindas = useCallback(async () => {
    await api.post("/auth/dispensar-banner-boas-vindas");
    setUsuario((atual) => {
      if (!atual) return atual;
      const atualizado = { ...atual, boas_vindas_banner_dispensado: true };
      atualizarUsuarioSalvo(atualizado);
      return atualizado;
    });
  }, []);

  const marcarTutorialModuloVisto = useCallback(async (modulo: string) => {
    // Raio-X 2026-09-24 (bug real reportado): NUNCA substituir `usuario`
    // pela resposta deste endpoint — `/auth/marcar-tutorial-modulo-visto`
    // devolve o `Usuario` cru do banco, sem `recursos_plano`/`tenant_tipo`
    // (campos só enriquecidos em `_resposta_token`, no login). Um
    // `setUsuario(resposta)` direto apagava `recursos_plano.modulo_*` da
    // sessão (voltavam ao default `False` do schema), escondendo CRM/MAP/
    // PREDATOR da sidebar até fazer logout/login de novo. Mesmo padrão
    // seguro de merge já usado por `dispensarBannerBoasVindas` etc. acima.
    await api.post("/auth/marcar-tutorial-modulo-visto", { modulo });
    setUsuario((atual) => {
      if (!atual || (atual.tutoriais_modulo_vistos ?? []).includes(modulo)) return atual;
      const atualizado = { ...atual, tutoriais_modulo_vistos: [...(atual.tutoriais_modulo_vistos ?? []), modulo] };
      atualizarUsuarioSalvo(atualizado);
      return atualizado;
    });
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({
      usuario,
      autenticado: Boolean(usuario && getToken()),
      temLicencaAtiva,
      entrar,
      entrarComGoogle,
      registrarVitrine,
      criarContaPublica,
      registrarComConvite,
      sair,
      primeiroLoginPendente,
      consumirPrimeiroLoginPendente,
      declararPagamento,
      confirmarAvisoWhatsappTemplate,
      atualizarWhatsappPessoal,
      dispensarBannerBoasVindas,
      marcarTutorialModuloVisto,
    }),
    [
      usuario,
      temLicencaAtiva,
      entrar,
      entrarComGoogle,
      registrarVitrine,
      criarContaPublica,
      registrarComConvite,
      sair,
      primeiroLoginPendente,
      consumirPrimeiroLoginPendente,
      declararPagamento,
      confirmarAvisoWhatsappTemplate,
      atualizarWhatsappPessoal,
      dispensarBannerBoasVindas,
      marcarTutorialModuloVisto,
    ],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth precisa estar dentro de <AuthProvider>");
  return context;
}
