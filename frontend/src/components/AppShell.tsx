import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";

import { InstallBanner } from "@/components/InstallBanner";
import { cn } from "@/lib/cn";
import { useAuth } from "@/lib/auth";

interface NavItem {
  path: string;
  label: string;
  icon: string;
  end?: boolean;
}

const NAV_ITEMS_PAGOS: NavItem[] = [
  { path: "/", label: "Dashboard", icon: "⬡", end: true },
  { path: "/map", label: "MAP", icon: "⚡" },
];

// CRM — o board (Pipeline) continua sendo a própria rota /crm; "Criar
// Proposta" é um submenu embaixo, revelado pela seta do NavGroup.
const CRM_ITEM: NavItem = { path: "/crm", label: "CRM", icon: "◈", end: true };
const CRM_SUBITENS: NavItem[] = [{ path: "/crm/propostas/nova", label: "Criar Proposta", icon: "📄" }];

// PREDATOR — motor de prospecção/cadências/campanhas. Sem rota própria
// (é só a categoria) — a seta expande/recolhe os módulos abaixo.
const PREDATOR_NAV_ITEMS: NavItem[] = [
  { path: "/prospeccao", label: "Prospecção", icon: "🎯" },
  { path: "/cadencias", label: "Cadências", icon: "📨" },
  { path: "/campanhas", label: "Campanhas", icon: "📣" },
  { path: "/aprovacoes", label: "Aprovações", icon: "✅" },
  { path: "/reunioes", label: "Reuniões", icon: "📅" },
  { path: "/configuracao", label: "Configuração", icon: "⚙" },
];

// Leads (E-Leads) — clientes avulsos cadastrados direto no CRM, fora do
// recorte de um ICP. Mesmo padrão de grupo indentado usado em ADMIN_NAV_ITEMS.
const LEADS_NAV_ITEMS: NavItem[] = [
  { path: "/leads/empresas", label: "Empresas", icon: "🏬" },
  { path: "/leads/contatos", label: "Contatos", icon: "🧑‍💼" },
];

// Sempre visível — é o único módulo que uma conta sem licença ativa
// (entrou via convite-vitrine, Onda H) tem acesso.
const NAV_ITEM_REDE_SOCIAL: NavItem = { path: "/rede-social", label: "Rede Social", icon: "◎", end: false };

// Tenants/Licenças: super_admin OU admin de um tenant distribuidor/
// revendedor gerenciando a própria subárvore (raio-X: hierarquia). Convites/
// Planos continuam exclusivos de super_admin — fora do escopo desta fase.
const ADMIN_NAV_ITEMS_HIERARQUIA: NavItem[] = [
  { path: "/admin/tenants", label: "Tenants", icon: "🏢" },
  { path: "/admin/licencas", label: "Licenças", icon: "📋" },
  { path: "/admin/relatorios", label: "Relatórios", icon: "📊" },
];
const ADMIN_NAV_ITEMS_SUPER_ADMIN: NavItem[] = [
  { path: "/admin/convites", label: "Convites", icon: "🔑" },
  { path: "/admin/planos", label: "Planos", icon: "💳" },
];
// API de provisionamento/billing (Fase 2 da hierarquia, raio-X) — exclusivo
// de admin de tenant tipo="distribuidor" (decisão validada com o usuário).
const ADMIN_NAV_ITEM_INTEGRACOES: NavItem = { path: "/admin/integracoes", label: "Integrações", icon: "🔌" };

const CLASSE_ITEM_BASE =
  "mb-0.5 flex items-center gap-2.5 rounded-lg border-l-2 border-transparent px-2.5 py-2 text-[12.5px] whitespace-nowrap text-muted transition-colors";
const CLASSE_ITEM_ATIVO = "border-cyan bg-cyan/15 font-bold text-cyan";
const CLASSE_ITEM_INATIVO = "hover:bg-white/3 hover:text-text";

function NavButton({ path, label, icon, end }: NavItem) {
  return (
    <NavLink
      to={path}
      end={end}
      className={({ isActive }) => cn(CLASSE_ITEM_BASE, isActive ? CLASSE_ITEM_ATIVO : CLASSE_ITEM_INATIVO)}
    >
      <span className="w-5 flex-shrink-0 text-center text-[15px]">{icon}</span>
      <span className="overflow-hidden text-ellipsis">{label}</span>
    </NavLink>
  );
}

/** Menu com submenus revelados por seta — mesmo peso visual dos itens de
 * topo (não mais um rótulo pequeno em uppercase). `path` é opcional: se
 * informado, o cabeçalho também navega (ex.: CRM); se omitido, o
 * cabeçalho só expande/recolhe (ex.: PREDATOR, que não é uma página). */
function NavGroup({ label, icon, path, itens }: { label: string; icon: string; path?: string; itens: NavItem[] }) {
  const location = useLocation();
  const algumFilhoAtivo = itens.some(
    (item) => location.pathname === item.path || location.pathname.startsWith(`${item.path}/`),
  );
  const [aberto, setAberto] = useState(algumFilhoAtivo);

  useEffect(() => {
    if (algumFilhoAtivo) setAberto(true);
  }, [algumFilhoAtivo]);

  const seta = (
    <button
      type="button"
      onClick={(event) => {
        event.preventDefault();
        setAberto((atual) => !atual);
      }}
      aria-label={aberto ? "Recolher submenu" : "Expandir submenu"}
      className="flex-shrink-0 rounded px-1 text-[10px] text-muted hover:text-text"
    >
      {aberto ? "▾" : "▸"}
    </button>
  );

  return (
    <div>
      {path ? (
        <div className="flex items-center gap-1">
          <NavLink
            to={path}
            end
            className={({ isActive }) =>
              cn(CLASSE_ITEM_BASE, "mb-0 flex-1", isActive || algumFilhoAtivo ? CLASSE_ITEM_ATIVO : CLASSE_ITEM_INATIVO)
            }
          >
            <span className="w-5 flex-shrink-0 text-center text-[15px]">{icon}</span>
            <span className="flex-1 overflow-hidden text-ellipsis">{label}</span>
          </NavLink>
          {seta}
        </div>
      ) : (
        <button
          type="button"
          onClick={() => setAberto((atual) => !atual)}
          className={cn(CLASSE_ITEM_BASE, "w-full", algumFilhoAtivo ? CLASSE_ITEM_ATIVO : CLASSE_ITEM_INATIVO)}
        >
          <span className="w-5 flex-shrink-0 text-center text-[15px]">{icon}</span>
          <span className="flex-1 overflow-hidden text-left text-ellipsis">{label}</span>
          <span className="flex-shrink-0 text-[10px]">{aberto ? "▾" : "▸"}</span>
        </button>
      )}
      {aberto && (
        <div className="mt-0.5 ml-4 flex flex-col gap-0.5 border-l border-border pl-2">
          {itens.map((item) => (
            <NavButton key={item.path} {...item} />
          ))}
        </div>
      )}
    </div>
  );
}

export function AppShell() {
  const { usuario, temLicencaAtiva, sair } = useAuth();
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const isSuperAdmin = usuario?.papel === "super_admin";
  const ehGestorHierarquico = usuario?.papel === "admin" && ["distribuidor", "revendedor"].includes(usuario.tenant_tipo);
  const ehAdminDistribuidor = usuario?.papel === "admin" && usuario.tenant_tipo === "distribuidor";
  const navItems = temLicencaAtiva
    ? [NAV_ITEMS_PAGOS[0], CRM_ITEM, ...CRM_SUBITENS, NAV_ITEMS_PAGOS[1], ...PREDATOR_NAV_ITEMS, NAV_ITEM_REDE_SOCIAL]
    : [NAV_ITEM_REDE_SOCIAL];

  return (
    <div className="flex h-screen overflow-hidden">
      <InstallBanner />

      <aside
        className={cn(
          "relative z-20 flex flex-shrink-0 flex-col overflow-hidden border-r border-border bg-surf transition-[width] duration-200",
          collapsed ? "w-[58px]" : "w-[220px]",
          "max-sm:fixed max-sm:h-full max-sm:w-[220px] max-sm:-translate-x-full max-sm:transition-transform",
          mobileOpen && "max-sm:translate-x-0",
        )}
      >
        <div className="flex items-center gap-2.5 border-b border-border p-3.5">
          <div className="flex h-8.5 w-8.5 flex-shrink-0 items-center justify-center rounded-lg bg-gradient-to-br from-cyan to-[#005F7A] font-head text-[17px] font-black text-bg">
            B
          </div>
          <div className="overflow-hidden whitespace-nowrap">
            <div className="font-head text-[15px] leading-none font-extrabold">
              B2B <span className="text-cyan">ON</span>
            </div>
            <div className="text-[9px] tracking-widest text-muted">OPERATING NETWORK</div>
          </div>
        </div>

        <nav className="flex-1 overflow-y-auto p-1.5">
          {temLicencaAtiva && <NavButton {...NAV_ITEMS_PAGOS[0]} />}

          {temLicencaAtiva && <NavGroup label={CRM_ITEM.label} icon={CRM_ITEM.icon} path={CRM_ITEM.path} itens={CRM_SUBITENS} />}

          {temLicencaAtiva && <NavButton {...NAV_ITEMS_PAGOS[1]} />}

          {temLicencaAtiva && <NavGroup label="Predator" icon="🐾" itens={PREDATOR_NAV_ITEMS} />}

          <NavButton {...NAV_ITEM_REDE_SOCIAL} />

          {temLicencaAtiva && (
            <>
              <div className="mt-3 mb-1 px-2.5 text-[9px] tracking-widest text-muted uppercase">Leads</div>
              {LEADS_NAV_ITEMS.map((item) => (
                <NavButton key={item.path} {...item} />
              ))}
            </>
          )}

          {(isSuperAdmin || ehGestorHierarquico) && (
            <>
              <div className="mt-3 mb-1 px-2.5 text-[9px] tracking-widest text-muted uppercase">Admin</div>
              {ADMIN_NAV_ITEMS_HIERARQUIA.map((item) => (
                <NavButton key={item.path} {...item} />
              ))}
              {ehAdminDistribuidor && <NavButton {...ADMIN_NAV_ITEM_INTEGRACOES} />}
              {isSuperAdmin && ADMIN_NAV_ITEMS_SUPER_ADMIN.map((item) => <NavButton key={item.path} {...item} />)}
            </>
          )}
        </nav>

        <div className="flex items-center gap-2.5 border-t border-border p-2.5">
          <div className="flex h-7.5 w-7.5 flex-shrink-0 items-center justify-center rounded-full bg-violet/15 text-xs font-bold text-violet">
            {usuario?.nome?.[0]?.toUpperCase() ?? "?"}
          </div>
          <div className="min-w-0 flex-1 overflow-hidden">
            <div className="overflow-hidden text-[12px] font-semibold text-ellipsis whitespace-nowrap">
              {usuario?.nome}
            </div>
            <div className="text-[9px] tracking-wide text-violet">{usuario?.papel?.toUpperCase()}</div>
          </div>
          <button onClick={sair} className="flex-shrink-0 text-[11px] text-muted hover:text-red">
            Sair
          </button>
        </div>

        <button
          className="absolute top-5 -right-2.75 z-30 flex h-5.5 w-5.5 items-center justify-center rounded-full border border-border bg-surf2 text-[11px] text-muted max-sm:hidden"
          onClick={() => setCollapsed((value) => !value)}
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
    </div>
  );
}
