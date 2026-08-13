import { useState } from "react";
import { NavLink, Outlet } from "react-router-dom";

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
  { path: "/crm", label: "CRM", icon: "◈" },
  { path: "/map", label: "MAP", icon: "⚡" },
];

// PREDATOR — motor de prospecção/cadências/campanhas. Grupo indentado
// exibido logo abaixo do MAP, mesmo padrão de LEADS_NAV_ITEMS/ADMIN_NAV_ITEMS.
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

const ADMIN_NAV_ITEMS: NavItem[] = [
  { path: "/admin/tenants", label: "Tenants", icon: "🏢" },
  { path: "/admin/licencas", label: "Licenças", icon: "📋" },
  { path: "/admin/convites", label: "Convites", icon: "🔑" },
  { path: "/admin/planos", label: "Planos", icon: "💳" },
];

function NavButton({ path, label, icon, end }: NavItem) {
  return (
    <NavLink
      to={path}
      end={end}
      className={({ isActive }) =>
        cn(
          "mb-0.5 flex items-center gap-2.5 rounded-lg border-l-2 border-transparent px-2.5 py-2 text-[12.5px] whitespace-nowrap text-muted transition-colors",
          isActive ? "border-cyan bg-cyan/15 font-bold text-cyan" : "hover:bg-white/3 hover:text-text",
        )
      }
    >
      <span className="w-5 flex-shrink-0 text-center text-[15px]">{icon}</span>
      <span className="overflow-hidden text-ellipsis">{label}</span>
    </NavLink>
  );
}

export function AppShell() {
  const { usuario, temLicencaAtiva, sair } = useAuth();
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const isSuperAdmin = usuario?.papel === "super_admin";
  const navItems = temLicencaAtiva
    ? [...NAV_ITEMS_PAGOS, ...PREDATOR_NAV_ITEMS, NAV_ITEM_REDE_SOCIAL]
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
          {temLicencaAtiva &&
            NAV_ITEMS_PAGOS.map((item) => <NavButton key={item.path} {...item} />)}

          {temLicencaAtiva && (
            <>
              <div className="mt-3 mb-1 px-2.5 text-[9px] tracking-widest text-muted uppercase">Predator</div>
              {PREDATOR_NAV_ITEMS.map((item) => (
                <NavButton key={item.path} {...item} />
              ))}
            </>
          )}

          <NavButton {...NAV_ITEM_REDE_SOCIAL} />

          {temLicencaAtiva && (
            <>
              <div className="mt-3 mb-1 px-2.5 text-[9px] tracking-widest text-muted uppercase">Leads</div>
              {LEADS_NAV_ITEMS.map((item) => (
                <NavButton key={item.path} {...item} />
              ))}
            </>
          )}

          {isSuperAdmin && (
            <>
              <div className="mt-3 mb-1 px-2.5 text-[9px] tracking-widest text-muted uppercase">Admin</div>
              {ADMIN_NAV_ITEMS.map((item) => (
                <NavButton key={item.path} {...item} />
              ))}
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
