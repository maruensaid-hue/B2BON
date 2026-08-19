import { lazy, Suspense } from "react";
import { Navigate, Route, Routes } from "react-router-dom";

import { AppShell } from "@/components/AppShell";
import { ProtectedRoute } from "@/components/ProtectedRoute";
import { ConviteVitrine } from "@/pages/ConviteVitrine";
import { Login } from "@/pages/Login";
import { PagamentoRetorno } from "@/pages/PagamentoRetorno";
import { RegistrarConvite } from "@/pages/RegistrarConvite";
import { Privacidade } from "@/pages/Privacidade";
import { Termos } from "@/pages/Termos";

// Rotas fora do bundle principal — cada uma vira seu próprio chunk, buscado
// só quando o usuário realmente navega até ali (ex.: Admin, que só existe
// pra super_admin, nunca precisa baixar pro resto dos usuários).
const AdminConvites = lazy(() => import("@/pages/admin/AdminConvites").then((m) => ({ default: m.AdminConvites })));
const AdminLicencas = lazy(() => import("@/pages/admin/AdminLicencas").then((m) => ({ default: m.AdminLicencas })));
const AdminPlanos = lazy(() => import("@/pages/admin/AdminPlanos").then((m) => ({ default: m.AdminPlanos })));
const AdminTenants = lazy(() => import("@/pages/admin/AdminTenants").then((m) => ({ default: m.AdminTenants })));
const Integracoes = lazy(() => import("@/pages/admin/Integracoes").then((m) => ({ default: m.Integracoes })));
const Aprovacoes = lazy(() => import("@/pages/aprovacoes/Aprovacoes").then((m) => ({ default: m.Aprovacoes })));
const Cadencias = lazy(() => import("@/pages/cadencias/Cadencias").then((m) => ({ default: m.Cadencias })));
const Campanhas = lazy(() => import("@/pages/campanhas/Campanhas").then((m) => ({ default: m.Campanhas })));
// Dashboard puxa o recharts (biblioteca de gráfico pesada) — só ela usa
// essa dependência, então separá-la em chunk próprio tira o peso do
// gráfico do bundle principal mesmo sendo a rota inicial (o shell da
// aplicação, com o menu, aparece antes do gráfico terminar de carregar).
const Dashboard = lazy(() => import("@/pages/Dashboard").then((m) => ({ default: m.Dashboard })));
const Configuracao = lazy(() => import("@/pages/configuracao/Configuracao").then((m) => ({ default: m.Configuracao })));
const CriarProposta = lazy(() => import("@/pages/crm/CriarProposta").then((m) => ({ default: m.CriarProposta })));
const Kanban = lazy(() => import("@/pages/crm/Kanban").then((m) => ({ default: m.Kanban })));
const LeadsAcoesConta = lazy(() => import("@/pages/leads/LeadsAcoesConta").then((m) => ({ default: m.LeadsAcoesConta })));
const LeadsContatos = lazy(() => import("@/pages/leads/LeadsContatos").then((m) => ({ default: m.LeadsContatos })));
const LeadsEmpresas = lazy(() => import("@/pages/leads/LeadsEmpresas").then((m) => ({ default: m.LeadsEmpresas })));
const Map = lazy(() => import("@/pages/map/Map").then((m) => ({ default: m.Map })));
const Prospeccao = lazy(() => import("@/pages/prospeccao/Prospeccao").then((m) => ({ default: m.Prospeccao })));
const RedeSocial = lazy(() => import("@/pages/rede-social/RedeSocial").then((m) => ({ default: m.RedeSocial })));
const Reunioes = lazy(() => import("@/pages/reunioes/Reunioes").then((m) => ({ default: m.Reunioes })));

function CarregandoPagina() {
  return <div className="p-5.5 text-[12px] text-muted">Carregando...</div>;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/convite-vitrine/:codigo" element={<ConviteVitrine />} />
      <Route path="/convite/:codigo" element={<RegistrarConvite />} />
      <Route path="/privacidade" element={<Privacidade />} />
      <Route path="/termos" element={<Termos />} />
      <Route path="/pagamento/retorno" element={<PagamentoRetorno />} />

      <Route element={<ProtectedRoute />}>
        <Route element={<AppShell />}>
          <Route
            index
            element={
              <Suspense fallback={<CarregandoPagina />}>
                <Dashboard />
              </Suspense>
            }
          />
          <Route
            path="crm"
            element={
              <Suspense fallback={<CarregandoPagina />}>
                <Kanban />
              </Suspense>
            }
          />
          <Route
            path="crm/propostas/nova"
            element={
              <Suspense fallback={<CarregandoPagina />}>
                <CriarProposta />
              </Suspense>
            }
          />
          <Route
            path="leads/empresas"
            element={
              <Suspense fallback={<CarregandoPagina />}>
                <LeadsEmpresas />
              </Suspense>
            }
          />
          <Route
            path="leads/contatos"
            element={
              <Suspense fallback={<CarregandoPagina />}>
                <LeadsContatos />
              </Suspense>
            }
          />
          <Route
            path="leads/contas/:id"
            element={
              <Suspense fallback={<CarregandoPagina />}>
                <LeadsAcoesConta />
              </Suspense>
            }
          />
          <Route
            path="rede-social"
            element={
              <Suspense fallback={<CarregandoPagina />}>
                <RedeSocial />
              </Suspense>
            }
          />
          <Route
            path="map"
            element={
              <Suspense fallback={<CarregandoPagina />}>
                <Map />
              </Suspense>
            }
          />
          <Route
            path="prospeccao"
            element={
              <Suspense fallback={<CarregandoPagina />}>
                <Prospeccao />
              </Suspense>
            }
          />
          <Route
            path="cadencias"
            element={
              <Suspense fallback={<CarregandoPagina />}>
                <Cadencias />
              </Suspense>
            }
          />
          <Route
            path="campanhas"
            element={
              <Suspense fallback={<CarregandoPagina />}>
                <Campanhas />
              </Suspense>
            }
          />
          <Route
            path="aprovacoes"
            element={
              <Suspense fallback={<CarregandoPagina />}>
                <Aprovacoes />
              </Suspense>
            }
          />
          <Route
            path="reunioes"
            element={
              <Suspense fallback={<CarregandoPagina />}>
                <Reunioes />
              </Suspense>
            }
          />
          <Route
            path="configuracao"
            element={
              <Suspense fallback={<CarregandoPagina />}>
                <Configuracao />
              </Suspense>
            }
          />
          <Route
            path="admin/tenants"
            element={
              <Suspense fallback={<CarregandoPagina />}>
                <AdminTenants />
              </Suspense>
            }
          />
          <Route
            path="admin/licencas"
            element={
              <Suspense fallback={<CarregandoPagina />}>
                <AdminLicencas />
              </Suspense>
            }
          />
          <Route
            path="admin/integracoes"
            element={
              <Suspense fallback={<CarregandoPagina />}>
                <Integracoes />
              </Suspense>
            }
          />
          <Route
            path="admin/convites"
            element={
              <Suspense fallback={<CarregandoPagina />}>
                <AdminConvites />
              </Suspense>
            }
          />
          <Route
            path="admin/planos"
            element={
              <Suspense fallback={<CarregandoPagina />}>
                <AdminPlanos />
              </Suspense>
            }
          />
        </Route>
      </Route>

      {/* URL sem rota correspondente (ex.: link de convite colado errado,
          duplicando o caminho) — antes disto o React não renderizava nada,
          uma tela em branco sem nenhum aviso (raio-X de produção real). */}
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
