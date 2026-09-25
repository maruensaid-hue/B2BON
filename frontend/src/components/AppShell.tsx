import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";

import { BuscaGlobal } from "@/components/busca/BuscaGlobal";
import { InstallBanner } from "@/components/InstallBanner";
import { PainelAjudaDocado } from "@/components/onboarding/PainelAjudaDocado";
import { TourGuiado } from "@/components/onboarding/TourGuiado";
import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import { api } from "@/lib/api";
import { cn } from "@/lib/cn";
import { useAuth } from "@/lib/auth";

interface NavItem {
  path: string;
  label: string;
  icon: string;
  end?: boolean;
  /** Resumo de 3-4 palavras mostrado no flyout do grupo (redesign
   * Salesforce, raio-X 2026-09-21) — não usado nos itens de topo soltos. */
  descricao?: string;
}

interface NotificacaoRedeSocial {
  id: number;
  tipo: string;
  referencia_tipo: string;
  referencia_id: number;
  mensagem: string;
  lida: boolean;
  criado_em: string;
}

const INTERVALO_POLLING_NOTIFICACOES_MS = 30_000;

const NAV_ITEMS_PAGOS: NavItem[] = [
  { path: "/", label: "Dashboard", icon: "⬡", end: true },
  { path: "/map", label: "MAP", icon: "⚡" },
];

// CRM — o board (Pipeline) continua sendo a própria rota /crm; "Criar
// Proposta" é um submenu embaixo, revelado pelo flyout do NavGroup.
const CRM_ITEM: NavItem = { path: "/crm", label: "CRM", icon: "◈", end: true, descricao: "Pipeline de negócios" };
const CRM_SUBITENS: NavItem[] = [
  { path: "/crm/propostas/nova", label: "Criar Proposta", icon: "📄", descricao: "Gerar proposta comercial" },
  { path: "/crm/receita", label: "Revenue Intelligence", icon: "📈", descricao: "Métricas de receita" },
];

// PREDATOR — motor de prospecção/cadências/campanhas. Sem rota própria
// (é só a categoria) — o flyout mostra os módulos abaixo.
const PREDATOR_NAV_ITEMS: NavItem[] = [
  { path: "/prospeccao", label: "Prospecção", icon: "🎯", descricao: "Listas de contas" },
  { path: "/cadencias", label: "Cadências", icon: "📨", descricao: "Sequências de toques" },
  { path: "/campanhas", label: "Campanhas", icon: "📣", descricao: "Disparo em massa" },
  { path: "/aprovacoes", label: "Aprovações", icon: "✅", descricao: "Revisar mensagens da IA" },
  { path: "/reunioes", label: "Reuniões", icon: "📅", descricao: "Lembretes e transcrição" },
  { path: "/agenda", label: "Agenda", icon: "🗓️", descricao: "Visão semanal de compromissos" },
  { path: "/webmail", label: "Webmail", icon: "📧", descricao: "E-mail direto com seus leads" },
  { path: "/relatorio-entrega", label: "Relatório de Entrega", icon: "📊", descricao: "Taxas de entrega" },
  { path: "/regras-aprendidas", label: "Regras Aprendidas", icon: "🧠", descricao: "Regras de estilo" },
  { path: "/inteligencia-rede", label: "Sinais de Oportunidade", icon: "🧭", descricao: "Fit e matches" },
  { path: "/agente-corporativo", label: "Agente Corporativo", icon: "🤖", descricao: "IA responde perguntas" },
  { path: "/configuracao", label: "Configuração", icon: "⚙", descricao: "Oferta e canais" },
];

// Leads (E-Leads) — clientes avulsos cadastrados direto no CRM, fora do
// recorte de um ICP. Mesmo padrão de grupo indentado usado em ADMIN_NAV_ITEMS.
const LEADS_NAV_ITEMS: NavItem[] = [
  { path: "/leads/empresas", label: "Empresas", icon: "🏬" },
  { path: "/leads/contatos", label: "Contatos", icon: "🧑‍💼" },
];

// Sempre visível — é o único módulo que uma conta sem licença ativa
// (entrou via convite-vitrine, Onda H) tem acesso.
const NAV_ITEM_REDE_SOCIAL: NavItem = { path: "/rede-social", label: "Shoal", icon: "◎", end: false };

// B2B ON Intelligence (Fase 4) — Corporate Brain do tenant, qualquer plano pago.
const NAV_ITEM_CEREBRO: NavItem = { path: "/inteligencia/cerebro", label: "Cérebro Corporativo", icon: "🧬" };

// Bid Intelligence (Fase 9) — só com o módulo "bids" (B2B ON Public Sector).
const NAV_ITEM_BIDS: NavItem = { path: "/bids", label: "Licitações", icon: "🏛", end: false };

// Public Procurement (Fase 10) — só com o módulo "procurement" (lado comprador).
const NAV_ITEM_COMPRAS: NavItem = { path: "/compras", label: "Compras públicas", icon: "🧾", end: false };

// RO (Registro de Oportunidade) — deal registration: qualquer papel
// registra/vê as próprias oportunidades; "Aprovar Descontos" é só de
// quem decide desconto pra toda a rede (admin do tenant raiz/distribuidor,
// mesma condição de `ehAdminDistribuidor` — distribuidor nunca tem pai,
// então é sempre a raiz da própria rede — ou super_admin).
const RO_NAV_ITEM: NavItem = { path: "/ro", label: "Minhas Oportunidades", icon: "📌" };
const RO_NAV_ITEM_APROVACOES: NavItem = { path: "/ro/aprovacoes", label: "Aprovar Descontos", icon: "💰" };

// Tenants/Licenças: super_admin OU admin de um tenant distribuidor/
// revendedor gerenciando a própria subárvore (raio-X: hierarquia). Planos/
// Verificações continuam exclusivos de super_admin (operação global, cross-
// tenant). "Convites" (convidar colega pro PRÓPRIO tenant) é escopado por
// tenant, sem nada de hierarquia — qualquer admin já pode gerar via API
// (`exigir_papel("super_admin", "admin")`); o nav ficava restrito a
// super_admin por engano, o que deixava um admin comum (ex.: dono de um
// tenant que só usa a Shoal, sem PREDATOR) sem como convidar um colega —
// corrigido junto com a trava de não poder conceder papel "super_admin"
// (`auth_service.gerar_convite`, achado ao abrir este nav pra admin comum).
const ADMIN_NAV_ITEMS_HIERARQUIA: NavItem[] = [
  { path: "/admin/tenants", label: "Tenants", icon: "🏢" },
  { path: "/admin/licencas", label: "Licenças", icon: "📋" },
  { path: "/admin/relatorios", label: "Relatórios", icon: "📊" },
];
const ADMIN_NAV_ITEM_CONVITES: NavItem = { path: "/admin/convites", label: "Convites", icon: "🔑" };
const ADMIN_NAV_ITEMS_SUPER_ADMIN: NavItem[] = [
  { path: "/admin/planos", label: "Planos", icon: "💳" },
  { path: "/admin/representantes", label: "Representantes", icon: "🤝" },
  { path: "/admin/verificacoes-empresa", label: "Verificações", icon: "🛡️" },
];
// API de provisionamento/billing (Fase 2 da hierarquia, raio-X) — exclusivo
// de admin de tenant tipo="distribuidor" (decisão validada com o usuário).
const ADMIN_NAV_ITEM_INTEGRACOES: NavItem = { path: "/admin/integracoes", label: "Integrações", icon: "🔌" };
const ADMIN_NAV_ITEM_API: NavItem = { path: "/admin/api", label: "API & Webhooks", icon: "🧩" };
const ADMIN_NAV_ITEM_IA: NavItem = { path: "/admin/ia", label: "IA & Créditos", icon: "💠" };
const ADMIN_NAV_ITEM_ASSINATURA: NavItem = { path: "/assinatura", label: "Assinatura", icon: "🧾" };

const CLASSE_ITEM_BASE =
  "mb-0.5 flex items-center gap-2.5 rounded-lg border-l-2 border-transparent px-2.5 py-2 text-[12.5px] whitespace-nowrap text-nav-muted transition-colors";
const CLASSE_ITEM_ATIVO = "border-cyan bg-cyan/15 font-bold text-cyan";
const CLASSE_ITEM_INATIVO = "hover:bg-nav-hover hover:text-nav-text";
// Ícone maior quando a sidebar está colapsada (raio-X 2026-09-21, pedido
// do usuário) — é o único elemento visual do item nesse estado, então
// precisa de mais destaque do que quando acompanhado do rótulo por extenso.
const CLASSE_ICONE_EXPANDIDO = "w-5 flex-shrink-0 text-center text-[14px]";
const CLASSE_ICONE_COLAPSADO = "w-6 flex-shrink-0 text-center text-[20px]";

function NavButton({ path, label, icon, end, collapsed }: NavItem & { collapsed?: boolean }) {
  return (
    <NavLink
      to={path}
      end={end}
      data-tour-id={`nav:${path}`}
      title={collapsed ? label : undefined}
      className={({ isActive }) =>
        cn(CLASSE_ITEM_BASE, collapsed && "justify-center px-0", isActive ? CLASSE_ITEM_ATIVO : CLASSE_ITEM_INATIVO)
      }
    >
      <span className={collapsed ? CLASSE_ICONE_COLAPSADO : CLASSE_ICONE_EXPANDIDO}>{icon}</span>
      {!collapsed && <span className="overflow-hidden text-ellipsis">{label}</span>}
    </NavLink>
  );
}

/** Item de dentro do flyout do `NavGroup` — mostra nome + um pequeno
 * descritivo (3-4 palavras) abaixo, não só o nome (redesign Salesforce,
 * raio-X 2026-09-21). Mantém `data-tour-id={nav:${path}}` igual ao
 * `NavButton`, pro Tour Guiado continuar achando o elemento. */
function FlyoutItem({ path, label, icon, end, descricao, onNavegar }: NavItem & { onNavegar: () => void }) {
  return (
    <NavLink
      to={path}
      end={end}
      data-tour-id={`nav:${path}`}
      onClick={onNavegar}
      className={({ isActive }) =>
        cn(
          "flex items-start gap-2.5 rounded-lg px-2.5 py-1.5 transition-colors",
          isActive ? "bg-cyan/15 text-cyan" : "text-nav-text hover:bg-nav-hover",
        )
      }
    >
      <span className="mt-0.5 w-5 flex-shrink-0 text-center text-[14px]">{icon}</span>
      <span className="flex min-w-0 flex-col">
        <span className="overflow-hidden text-[12.5px] font-semibold text-ellipsis whitespace-nowrap">{label}</span>
        {descricao && (
          <span className="overflow-hidden text-[10px] text-nav-muted text-ellipsis whitespace-nowrap">
            {descricao}
          </span>
        )}
      </span>
    </NavLink>
  );
}

/** Menu com submenus revelados por um flyout ao lado do ícone — sempre
 * disponível assim, colapsada ou expandida (redesign Salesforce, raio-X
 * 2026-09-21; antes só existia flyout colapsado, e a sidebar expandida
 * usava uma lista inline que foi removida). `path` é opcional: se
 * informado, o cabeçalho do flyout também navega (ex.: CRM); se omitido,
 * o cabeçalho é só um rótulo (ex.: PREDATOR, que não é uma página).
 * `tourToggleId`: marca o botão-gatilho com `data-tour-toggle`, pro Tour
 * Guiado (`TourGuiado.tsx`) conseguir abrir o flyout sozinho antes de
 * destacar um item de dentro dele (ex.: "visita detalhada" ao PREDATOR —
 * cada sub-módulo vira um passo do tour). */
function NavGroup({
  label,
  icon,
  path,
  itens,
  tourToggleId,
  collapsed,
  descricao,
}: {
  label: string;
  icon: string;
  path?: string;
  itens: NavItem[];
  tourToggleId?: string;
  collapsed?: boolean;
  descricao?: string;
}) {
  const location = useLocation();
  const algumFilhoAtivo = itens.some(
    (item) => location.pathname === item.path || location.pathname.startsWith(`${item.path}/`),
  );
  const [flyoutAberto, setFlyoutAberto] = useState(false);
  const [flyoutPos, setFlyoutPos] = useState<{ top: number; left: number } | null>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const flyoutRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!flyoutAberto) return;
    function aoClicarFora(evento: MouseEvent) {
      const alvo = evento.target as Node;
      if (triggerRef.current?.contains(alvo) || flyoutRef.current?.contains(alvo)) return;
      setFlyoutAberto(false);
    }
    function aoTeclar(evento: KeyboardEvent) {
      if (evento.key === "Escape") setFlyoutAberto(false);
    }
    document.addEventListener("mousedown", aoClicarFora);
    document.addEventListener("keydown", aoTeclar);
    return () => {
      document.removeEventListener("mousedown", aoClicarFora);
      document.removeEventListener("keydown", aoTeclar);
    };
  }, [flyoutAberto]);

  function alternarFlyout() {
    if (!flyoutAberto && triggerRef.current) {
      const retangulo = triggerRef.current.getBoundingClientRect();
      setFlyoutPos({ top: retangulo.top, left: retangulo.right + 6 });
    }
    setFlyoutAberto((atual) => !atual);
  }

  // Com muitos sub-itens (ex.: Predator, 11), o flyout aberto perto do
  // fim da sidebar pode nascer com o rodapé fora da viewport, sem
  // como rolar até lá — reposiciona pra cima depois de medir a altura
  // real renderizada (raio-X 2026-09-21).
  useLayoutEffect(() => {
    if (!flyoutAberto || !flyoutRef.current) return;
    const retangulo = flyoutRef.current.getBoundingClientRect();
    const estouro = retangulo.bottom - (window.innerHeight - 8);
    if (estouro > 0) {
      setFlyoutPos((atual) => (atual ? { ...atual, top: Math.max(8, atual.top - estouro) } : atual));
    }
  }, [flyoutAberto]);

  return (
    <div>
      <button
        ref={triggerRef}
        type="button"
        data-tour-toggle={tourToggleId}
        title={collapsed ? label : undefined}
        onClick={alternarFlyout}
        className={cn(
          CLASSE_ITEM_BASE,
          "w-full",
          collapsed && "justify-center px-0",
          algumFilhoAtivo ? CLASSE_ITEM_ATIVO : CLASSE_ITEM_INATIVO,
        )}
      >
        <span className={collapsed ? CLASSE_ICONE_COLAPSADO : CLASSE_ICONE_EXPANDIDO}>{icon}</span>
        {!collapsed && (
          <>
            <span className="flex-1 overflow-hidden text-left text-ellipsis">{label}</span>
            <span className="flex-shrink-0 text-[10px]">▸</span>
          </>
        )}
      </button>
      {flyoutAberto &&
        flyoutPos &&
        createPortal(
          <div
            ref={flyoutRef}
            className="fixed z-40 w-60 overflow-y-auto rounded-lg border border-nav-border bg-nav-bg p-1.5 shadow-xl"
            style={{ top: flyoutPos.top, left: flyoutPos.left, maxHeight: "calc(100vh - 16px)" }}
          >
            {path ? (
              <NavLink
                to={path}
                end
                onClick={() => setFlyoutAberto(false)}
                className={({ isActive }) =>
                  cn(
                    "mb-1 flex items-start gap-2.5 rounded-lg px-2.5 py-1.5 transition-colors",
                    isActive ? "bg-cyan/15 text-cyan" : "text-nav-text hover:bg-nav-hover",
                  )
                }
              >
                <span className="mt-0.5 w-5 flex-shrink-0 text-center text-[14px]">{icon}</span>
                <span className="flex flex-col">
                  <span className="text-[12.5px] font-bold">{label}</span>
                  {descricao && <span className="text-[10px] text-nav-muted">{descricao}</span>}
                </span>
              </NavLink>
            ) : (
              <div className="mb-1 flex items-start gap-2.5 px-2.5 py-1">
                <span className="mt-0.5 w-5 flex-shrink-0 text-center text-[14px]">{icon}</span>
                <span className="flex flex-col">
                  <span className="text-[12.5px] font-bold text-nav-text">{label}</span>
                  {descricao && <span className="text-[10px] text-nav-muted">{descricao}</span>}
                </span>
              </div>
            )}
            <div className="flex flex-col gap-0.5 border-t border-nav-border pt-1">
              {itens.map((item) => (
                <FlyoutItem key={item.path} {...item} onNavegar={() => setFlyoutAberto(false)} />
              ))}
            </div>
          </div>,
          document.body,
        )}
    </div>
  );
}

function BannerLicencaSuspensa() {
  const { declararPagamento } = useAuth();
  const [statusLicenca, setStatusLicenca] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [confirmado, setConfirmado] = useState(false);

  useEffect(() => {
    // `temLicencaAtiva=false` também cobre quem nunca teve licença paga
    // (convite-vitrine gratuito) — só faz sentido oferecer "já paguei"
    // pra quem de fato está "suspensa" por inadimplência.
    api
      .get<{ status: string }>("/auth/licenca-status")
      .then((resposta) => setStatusLicenca(resposta.status))
      .catch(() => setStatusLicenca(null));
  }, []);

  async function aoClicar() {
    setEnviando(true);
    setErro(null);
    try {
      await declararPagamento();
      setConfirmado(true);
    } catch {
      setErro("Não foi possível registrar agora. Tente de novo em alguns instantes.");
    } finally {
      setEnviando(false);
    }
  }

  if (statusLicenca !== "suspensa" || confirmado) return null;

  return (
    <div className="flex flex-wrap items-center gap-3 border-b border-amber/30 bg-amber/10 px-4 py-2.5 text-[12.5px] text-text">
      <span className="flex-1">
        Sua licença está suspensa por falta de pagamento. Se você já pagou e o pagamento ainda está em
        compensação (boleto ou cartão), avise a gente para liberar seu acesso enquanto confirmamos.
      </span>
      {erro && <span className="text-red">{erro}</span>}
      <button
        type="button"
        onClick={aoClicar}
        disabled={enviando}
        className="flex-shrink-0 rounded-lg bg-amber px-3 py-1.5 font-semibold text-white disabled:opacity-60"
      >
        {enviando ? "Enviando..." : "Já fiz o pagamento"}
      </button>
    </div>
  );
}

/** Pop-up de canal de e-mail pausado por bounce/spam (raio-X 2026-09-16,
 * Relatório de Entrega) — `reputacao_service` já pausava o canal
 * automaticamente antes disso, mas nada avisava o usuário na tela; sem
 * isso, campanhas/cadências de e-mail simplesmente paravam de sair sem
 * explicação nenhuma visível. Fecha só pra esta sessão — reabre no
 * próximo login/reload enquanto o canal continuar pausado (diferente do
 * aviso de template do WhatsApp, que é "confirme que já leu" e some pra
 * sempre: aqui é um bloqueio operacional real, não uma leitura única). */
function AvisoCanalEmailPausado() {
  const navigate = useNavigate();
  const [pausado, setPausado] = useState(false);
  const [taxaBounce, setTaxaBounce] = useState<number | null>(null);
  const [aberto, setAberto] = useState(true);

  useEffect(() => {
    api
      .get<{ pausado: boolean; taxa_bounce: number }>("/canais/email/saude")
      .then((resposta) => {
        setPausado(resposta.pausado);
        setTaxaBounce(resposta.taxa_bounce);
      })
      .catch(() => undefined);
  }, []);

  if (!pausado || !aberto) return null;

  return (
    <Modal title="Canal de e-mail pausado por reputação" open onClose={() => setAberto(false)}>
      <div className="flex flex-col gap-3 text-[12.5px]">
        <p>
          O envio de e-mail deste tenant foi pausado automaticamente
          {taxaBounce !== null && ` (taxa de bounce de ${(taxaBounce * 100).toFixed(1)}%)`} — acima do limite
          seguro pra não comprometer a reputação do domínio e cair em SPAM. Novas campanhas e cadências de e-mail
          não podem ser ativadas enquanto isso não for resolvido.
        </p>
        <p>
          Corrija ou exclua os contatos com e-mail inválido no Relatório de Entrega e reative o canal por lá.
        </p>
        <Button
          onClick={() => {
            setAberto(false);
            navigate("/relatorio-entrega");
          }}
          className="mt-1 w-full justify-center"
        >
          Ver Relatório de Entrega
        </Button>
      </div>
    </Modal>
  );
}

/** Aviso proativo (raio-X 2026-09-15) — nudge leve, não bloqueante, pro
 * vendedor que tem conta(s) atribuída(s) mas ainda não cadastrou o
 * WhatsApp pessoal em "Meu Perfil": sem esse número, o botão de
 * redirecionamento dos templates de WhatsApp não leva a lugar nenhum.
 * Descartável só pela sessão atual — reaparece num F5, de propósito,
 * até a pessoa de fato preencher o número (diferente do aviso de
 * template, que é "confirme que já leu" e fica salvo pra sempre). */
function AvisoWhatsappPessoalFaltando() {
  const { usuario } = useAuth();
  const [dispensado, setDispensado] = useState(false);

  if (dispensado || !usuario?.tem_conta_atribuida || usuario.whatsapp_pessoal) return null;

  return (
    <div className="flex flex-wrap items-center gap-3 border-b border-cyan/30 bg-cyan/10 px-4 py-2.5 text-[12.5px] text-text">
      <span className="flex-1">
        Você ainda não cadastrou seu WhatsApp pessoal — sem ele, o botão de redirecionamento dos templates de
        WhatsApp da cadência não leva o cliente a lugar nenhum.
      </span>
      <NavLink to="/perfil" className="flex-shrink-0 rounded-lg bg-cyan px-3 py-1.5 font-semibold text-white">
        Cadastrar agora
      </NavLink>
      <button onClick={() => setDispensado(true)} className="flex-shrink-0 text-[11px] text-muted hover:text-text">
        Depois
      </button>
    </div>
  );
}

export function AppShell() {
  const { usuario, temLicencaAtiva, sair, primeiroLoginPendente, consumirPrimeiroLoginPendente } = useAuth();
  const navegar = useNavigate();
  // Logout leva pra Central de Negócios, não direto pro login (raio-X
  // 2026-09-21, página de boas-vindas) — mantém o visitante recém-saído
  // vendo conteúdo da plataforma em vez de cair numa tela em branco.
  //
  // Bug real encontrado 2026-09-21: chamar `sair()` e `navegar(...)` juntos
  // (mesmo com `setTimeout(sair, 0)`) deixava `ProtectedRoute` reagir ao
  // `autenticado=false` antes do React terminar de desmontar este
  // `AppShell` — ele empurrava um `<Navigate to="/login" replace/>` que
  // sobrescrevia a navegação pra Central de Negócios já em andamento,
  // mandando o usuário pro login em vez da página pública (confirmado com
  // instrumentação de `history.pushState`/`replaceState`: mesmo com o
  // `setTimeout`, a ordem de commit do React não garantia que o
  // `ProtectedRoute` já tivesse desmontado antes do timeout disparar).
  // Fix: só chama `sair()` no CLEANUP do `useEffect` deste componente —
  // sinal 100% determinístico de que o `AppShell` (e o `ProtectedRoute`
  // que o envolve) já desmontou de verdade, então não sobra mais nada
  // reagindo à sessão sendo limpa.
  const sairPendenteRef = useRef(false);
  useEffect(() => {
    return () => {
      if (sairPendenteRef.current) sair();
    };
  }, [sair]);
  function sairEVerConteudo() {
    sairPendenteRef.current = true;
    navegar("/central-de-negocios");
  }
  // Rail icon-only (redesign Salesforce, raio-X 2026-09-21) — persistido
  // pra não perder o ganho de espaço a cada reload.
  const [collapsed, setCollapsed] = useState(() => localStorage.getItem("b2bon_sidebar_collapsed") === "true");
  function alternarCollapsed() {
    setCollapsed((atual) => {
      const novo = !atual;
      localStorage.setItem("b2bon_sidebar_collapsed", String(novo));
      return novo;
    });
  }
  const [mobileOpen, setMobileOpen] = useState(false);
  const [tourAberto, setTourAberto] = useState(false);
  // Painel de IA docado (raio-X 2026-09-21, consolida o antigo FaqModal):
  // minimizado por padrão, persiste aberto/fechado entre navegações via
  // localStorage — a transcrição em si não é persistida (só o boolean).
  const [painelAjudaAberto, setPainelAjudaAberto] = useState(
    () => localStorage.getItem("b2bon_painel_ajuda_aberto") === "true",
  );
  function alternarPainelAjuda(aberto: boolean) {
    setPainelAjudaAberto(aberto);
    localStorage.setItem("b2bon_painel_ajuda_aberto", String(aberto));
  }
  const [buscaAberta, setBuscaAberta] = useState(false);
  const [notificacoesAbertas, setNotificacoesAbertas] = useState(false);
  const [notificacoes, setNotificacoes] = useState<NotificacaoRedeSocial[]>([]);
  const [contagemNaoLidas, setContagemNaoLidas] = useState(0);
  // `key` do TourGuiado — incrementado toda vez que o tour (re)abre, pra
  // forçar o React a remontar o componente do zero (raio-X 2026-09-01:
  // sem isto, reabrir via "Refazer o tour" quando `tourAberto` já
  // estivesse `true` não disparava o efeito de reset — `useEffect([open])`
  // só roda quando o valor muda —, deixando o passo travado no fim).
  const [tourKey, setTourKey] = useState(0);

  function abrirTour() {
    setTourKey((atual) => atual + 1);
    setTourAberto(true);
  }

  // Dispara o tour guiado automaticamente uma única vez, logo após o
  // primeiro login/cadastro (raio-X 2026-09-01) — consome o sinal na
  // hora pra não reabrir sozinho num F5 no meio da sessão.
  useEffect(() => {
    if (primeiroLoginPendente) {
      abrirTour();
      consumirPrimeiroLoginPendente();
    }
  }, [primeiroLoginPendente, consumirPrimeiroLoginPendente]);

  // Busca global (Ctrl+K/Cmd+K) — único listener de teclado global do app
  // hoje é o Escape do TourGuiado (condicionado a `open`), sem conflito.
  useEffect(() => {
    function aoTeclar(evento: KeyboardEvent) {
      if ((evento.metaKey || evento.ctrlKey) && evento.key.toLowerCase() === "k") {
        evento.preventDefault();
        setBuscaAberta(true);
      }
    }
    window.addEventListener("keydown", aoTeclar);
    return () => window.removeEventListener("keydown", aoTeclar);
  }, []);

  // Notificações da Rede Social (master prompt §65, Fase 2D) — polling
  // simples a cada 30s, sem WebSocket/SSE (infra de tempo real fora de
  // escopo desta fase). Rede Social é livre pra qualquer tenant (mesmo
  // sem licença ativa), então o sino independe de `temLicencaAtiva`.
  useEffect(() => {
    if (!usuario) return;
    async function buscarContagem() {
      try {
        const resposta = await api.get<{ total: number }>("/rede-social/notificacoes/contagem-nao-lidas");
        setContagemNaoLidas(resposta.total);
      } catch {
        // silencioso — não é crítico o suficiente pra interromper a navegação
      }
    }
    buscarContagem();
    const intervalo = setInterval(buscarContagem, INTERVALO_POLLING_NOTIFICACOES_MS);
    return () => clearInterval(intervalo);
  }, [usuario]);

  async function abrirNotificacoes() {
    const abrindo = !notificacoesAbertas;
    setNotificacoesAbertas(abrindo);
    if (abrindo) {
      try {
        setNotificacoes(await api.get<NotificacaoRedeSocial[]>("/rede-social/notificacoes"));
      } catch {
        // silencioso — igual ao polling de contagem
      }
    }
  }

  async function marcarNotificacaoLida(id: number) {
    try {
      await api.post(`/rede-social/notificacoes/${id}/marcar-lida`);
      setNotificacoes((atual) => atual.map((n) => (n.id === id ? { ...n, lida: true } : n)));
      setContagemNaoLidas((atual) => Math.max(0, atual - 1));
    } catch {
      // silencioso
    }
  }

  async function marcarTodasNotificacoesLidas() {
    try {
      await api.post("/rede-social/notificacoes/marcar-todas-lidas");
      setNotificacoes((atual) => atual.map((n) => ({ ...n, lida: true })));
      setContagemNaoLidas(0);
    } catch {
      // silencioso
    }
  }

  const isSuperAdmin = usuario?.papel === "super_admin";
  const isAdmin = usuario?.papel === "admin";
  const ehGestorHierarquico = usuario?.papel === "admin" && ["distribuidor", "revendedor"].includes(usuario.tenant_tipo);
  const ehAdminDistribuidor = usuario?.papel === "admin" && usuario.tenant_tipo === "distribuidor";
  const temModuloMap = temLicencaAtiva && (usuario?.recursos_plano.modulo_map ?? false);
  const temModuloPredator = temLicencaAtiva && (usuario?.recursos_plano.modulo_predator ?? false);
  const temModuloCrm = temLicencaAtiva && (usuario?.recursos_plano.modulo_crm ?? false);
  const temModuloBids = temLicencaAtiva && (usuario?.recursos_plano.modulo_bids ?? false);
  const temModuloCompras = temLicencaAtiva && (usuario?.recursos_plano.modulo_procurement ?? false);
  const navItems = temLicencaAtiva
    ? [
        NAV_ITEMS_PAGOS[0],
        ...(temModuloCrm ? [CRM_ITEM, ...CRM_SUBITENS] : []),
        ...(temModuloMap ? [NAV_ITEMS_PAGOS[1]] : []),
        ...(temModuloPredator ? PREDATOR_NAV_ITEMS : []),
        ...(temModuloBids ? [NAV_ITEM_BIDS] : []),
        ...(temModuloCompras ? [NAV_ITEM_COMPRAS] : []),
        NAV_ITEM_REDE_SOCIAL,
        NAV_ITEM_CEREBRO,
      ]
    : [NAV_ITEM_REDE_SOCIAL];

  return (
    <div className="flex h-screen overflow-hidden">
      <InstallBanner />

      <aside
        className={cn(
          "relative z-20 flex flex-shrink-0 flex-col overflow-hidden border-r border-nav-border bg-nav-bg transition-[width] duration-200",
          collapsed ? "w-[58px]" : "w-[220px]",
          "max-sm:fixed max-sm:h-full max-sm:w-[220px] max-sm:-translate-x-full max-sm:transition-transform",
          mobileOpen && "max-sm:translate-x-0",
        )}
      >
        <div className="flex items-center gap-2.5 border-b border-nav-border p-3.5">
          <div className="flex h-8.5 w-8.5 flex-shrink-0 items-center justify-center rounded-lg bg-gradient-to-br from-cyan to-[#005F7A] font-head text-[17px] font-black text-white">
            B
          </div>
          {!collapsed && (
            <div className="overflow-hidden whitespace-nowrap">
              <div className="font-head text-[15px] leading-none font-extrabold text-nav-text">
                B2B <span className="text-cyan">ON</span>
              </div>
              <div className="text-[9px] tracking-widest text-nav-muted">OPERATING NETWORK</div>
            </div>
          )}
        </div>

        <nav className="flex-1 overflow-y-auto p-1.5">
          <button
            type="button"
            onClick={() => setBuscaAberta(true)}
            title={collapsed ? "Buscar" : undefined}
            className={cn(
              "mb-1.5 flex w-full items-center gap-2.5 rounded-lg border-l-2 border-transparent px-2.5 py-2 text-[12.5px] text-nav-muted transition-colors hover:bg-nav-hover hover:text-nav-text",
              collapsed && "justify-center px-0",
            )}
          >
            <span className={collapsed ? CLASSE_ICONE_COLAPSADO : CLASSE_ICONE_EXPANDIDO}>🔍</span>
            {!collapsed && (
              <>
                <span className="flex-1 overflow-hidden text-left text-ellipsis">Buscar</span>
                <span className="flex-shrink-0 rounded border border-nav-border px-1 text-[9px] text-nav-muted">
                  Ctrl K
                </span>
              </>
            )}
          </button>

          <div className="relative mb-1.5">
            <button
              type="button"
              onClick={abrirNotificacoes}
              title={collapsed ? "Notificações" : undefined}
              className={cn(
                "flex w-full items-center gap-2.5 rounded-lg border-l-2 border-transparent px-2.5 py-2 text-[12.5px] text-nav-muted transition-colors hover:bg-nav-hover hover:text-nav-text",
                collapsed && "justify-center px-0",
              )}
            >
              <span className={collapsed ? CLASSE_ICONE_COLAPSADO : CLASSE_ICONE_EXPANDIDO}>🔔</span>
              {!collapsed && <span className="flex-1 overflow-hidden text-left text-ellipsis">Notificações</span>}
              {contagemNaoLidas > 0 && (
                <span className="flex-shrink-0 rounded-full bg-red px-1.5 text-[9px] font-semibold text-white">
                  {contagemNaoLidas}
                </span>
              )}
            </button>
            {notificacoesAbertas && (
              <div className="absolute left-0 top-full z-30 mt-1 w-[280px] rounded-lg border border-border bg-surf p-2 shadow-lg">
                <div className="mb-1.5 flex items-center justify-between px-1">
                  <span className="text-[11px] font-semibold text-text">Notificações</span>
                  {contagemNaoLidas > 0 && (
                    <button type="button" onClick={marcarTodasNotificacoesLidas} className="text-[10px] text-cyan">
                      Marcar todas como lidas
                    </button>
                  )}
                </div>
                <div className="flex max-h-[320px] flex-col gap-1 overflow-y-auto">
                  {notificacoes.map((notificacao) => (
                    <button
                      key={notificacao.id}
                      type="button"
                      onClick={() => !notificacao.lida && marcarNotificacaoLida(notificacao.id)}
                      className={cn(
                        "rounded-md p-1.5 text-left text-[11px] text-text",
                        notificacao.lida ? "opacity-60" : "bg-surf2",
                      )}
                    >
                      <div>{notificacao.mensagem}</div>
                      <div className="text-[9px] text-muted">
                        {new Date(notificacao.criado_em).toLocaleString("pt-BR")}
                      </div>
                    </button>
                  ))}
                  {notificacoes.length === 0 && (
                    <div className="p-1.5 text-[11px] text-muted">Nenhuma notificação ainda.</div>
                  )}
                </div>
              </div>
            )}
          </div>

          {temLicencaAtiva && (
            <div data-tour-id="dashboard">
              <NavButton {...NAV_ITEMS_PAGOS[0]} collapsed={collapsed} />
            </div>
          )}

          {temModuloCrm && (
            <div data-tour-id="crm">
              <NavGroup
                label={CRM_ITEM.label}
                icon={CRM_ITEM.icon}
                path={CRM_ITEM.path}
                itens={CRM_SUBITENS}
                collapsed={collapsed}
                descricao={CRM_ITEM.descricao}
              />
            </div>
          )}

          {temModuloMap && (
            <div data-tour-id="map">
              <NavButton {...NAV_ITEMS_PAGOS[1]} collapsed={collapsed} />
            </div>
          )}

          {temModuloPredator && (
            <div data-tour-id="predator">
              <NavGroup
                label="Predator"
                icon="🐾"
                itens={PREDATOR_NAV_ITEMS}
                tourToggleId="predator"
                collapsed={collapsed}
                descricao="Motor de prospecção"
              />
            </div>
          )}

          <div data-tour-id="rede-social">
            <NavButton {...NAV_ITEM_REDE_SOCIAL} collapsed={collapsed} />
          </div>

          {temLicencaAtiva && <NavButton {...NAV_ITEM_CEREBRO} collapsed={collapsed} />}

          {temModuloPredator && (
            <div data-tour-id="leads">
              {!collapsed && (
                <div className="mt-3 mb-1 px-2.5 text-[9px] tracking-widest text-nav-muted uppercase">Leads</div>
              )}
              {LEADS_NAV_ITEMS.map((item) => (
                <NavButton key={item.path} {...item} collapsed={collapsed} />
              ))}
            </div>
          )}

          {temModuloPredator && (usuario?.recursos_plano.registro_oportunidade || isSuperAdmin) && (
            <div data-tour-id="ro">
              {!collapsed && (
                <div className="mt-3 mb-1 px-2.5 text-[9px] tracking-widest text-nav-muted uppercase">RO</div>
              )}
              <NavButton {...RO_NAV_ITEM} collapsed={collapsed} />
              {(ehAdminDistribuidor || isSuperAdmin) && (
                <NavButton {...RO_NAV_ITEM_APROVACOES} collapsed={collapsed} />
              )}
            </div>
          )}

          {(isSuperAdmin || ehGestorHierarquico || isAdmin) && (
            <div data-tour-id="admin">
              {!collapsed && (
                <div className="mt-3 mb-1 px-2.5 text-[9px] tracking-widest text-nav-muted uppercase">Admin</div>
              )}
              {(isSuperAdmin || ehGestorHierarquico) &&
                ADMIN_NAV_ITEMS_HIERARQUIA.map((item) => (
                  <NavButton key={item.path} {...item} collapsed={collapsed} />
                ))}
              {ehAdminDistribuidor && <NavButton {...ADMIN_NAV_ITEM_INTEGRACOES} collapsed={collapsed} />}
              {(isAdmin || isSuperAdmin) && <NavButton {...ADMIN_NAV_ITEM_API} collapsed={collapsed} />}
              {(isAdmin || isSuperAdmin) && <NavButton {...ADMIN_NAV_ITEM_IA} collapsed={collapsed} />}
              {(isAdmin || isSuperAdmin) && <NavButton {...ADMIN_NAV_ITEM_ASSINATURA} collapsed={collapsed} />}
              <NavButton {...ADMIN_NAV_ITEM_CONVITES} collapsed={collapsed} />
              {isSuperAdmin &&
                ADMIN_NAV_ITEMS_SUPER_ADMIN.map((item) => <NavButton key={item.path} {...item} collapsed={collapsed} />)}
            </div>
          )}
        </nav>

        {collapsed ? (
          <div className="flex flex-col items-center gap-1.5 border-t border-nav-border p-2.5">
            <NavLink
              to="/perfil"
              title="Meu Perfil"
              className="flex h-7.5 w-7.5 flex-shrink-0 items-center justify-center rounded-full bg-violet/25 text-xs font-bold text-violet"
            >
              {usuario?.nome?.[0]?.toUpperCase() ?? "?"}
            </NavLink>
            <button onClick={sairEVerConteudo} title="Sair" className="text-[13px] text-nav-muted hover:text-red">
              ⏻
            </button>
          </div>
        ) : (
          <div className="flex items-center gap-2.5 border-t border-nav-border p-2.5">
            <NavLink to="/perfil" className="flex h-7.5 w-7.5 flex-shrink-0 items-center justify-center rounded-full bg-violet/25 text-xs font-bold text-violet">
              {usuario?.nome?.[0]?.toUpperCase() ?? "?"}
            </NavLink>
            <NavLink to="/perfil" className="min-w-0 flex-1 overflow-hidden">
              <div className="overflow-hidden text-[12px] font-semibold text-ellipsis whitespace-nowrap text-nav-text">
                {usuario?.nome}
              </div>
              <div className="text-[9px] tracking-wide text-nav-muted">{usuario?.papel?.toUpperCase()}</div>
            </NavLink>
            <button onClick={sairEVerConteudo} className="flex-shrink-0 text-[11px] text-nav-muted hover:text-red">
              Sair
            </button>
          </div>
        )}

        <button
          className="absolute top-5 -right-2.75 z-30 flex h-5.5 w-5.5 items-center justify-center rounded-full border border-border bg-surf2 text-[11px] text-muted max-sm:hidden"
          onClick={alternarCollapsed}
        >
          {collapsed ? "›" : "‹"}
        </button>
      </aside>

      {mobileOpen && (
        <div className="fixed inset-0 z-10 bg-black/50 sm:hidden" onClick={() => setMobileOpen(false)} />
      )}

      <div className="flex flex-1 flex-col overflow-hidden">
        <header className="flex items-center gap-3 border-b border-border p-3 sm:hidden">
          <button onClick={() => setMobileOpen(true)} className="text-lg text-text">
            ☰
          </button>
          <div className="font-head text-sm font-bold">B2B ON</div>
        </header>

        {!temLicencaAtiva && <BannerLicencaSuspensa />}
        {temLicencaAtiva && <AvisoWhatsappPessoalFaltando />}
        {temLicencaAtiva && <AvisoCanalEmailPausado />}

        <main className="flex-1 overflow-auto pb-20 sm:pb-0">
          <Outlet />
        </main>
      </div>

      <nav className="fixed right-0 bottom-0 left-0 z-50 hidden justify-around border-t border-border bg-surf2/95 px-1 py-1.5 backdrop-blur-md max-sm:flex">
        {navItems.map((item) => (
          <NavLink
            key={item.path}
            to={item.path}
            end={item.end}
            className={({ isActive }) =>
              cn(
                "flex flex-1 flex-col items-center gap-0.5 py-1 text-[9px]",
                isActive ? "text-cyan" : "text-muted",
              )
            }
          >
            <span className="text-lg">{item.icon}</span>
            <span>{item.label}</span>
          </NavLink>
        ))}
      </nav>

      <BuscaGlobal open={buscaAberta} onClose={() => setBuscaAberta(false)} />
      <TourGuiado key={tourKey} open={tourAberto} onClose={() => setTourAberto(false)} />
      <PainelAjudaDocado
        open={painelAjudaAberto}
        onOpen={() => alternarPainelAjuda(true)}
        onClose={() => alternarPainelAjuda(false)}
        onRefazerTour={() => {
          alternarPainelAjuda(false);
          abrirTour();
        }}
      />
    </div>
  );
}
