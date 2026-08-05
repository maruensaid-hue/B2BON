import { Route, Routes } from "react-router-dom";

import { AppShell } from "@/components/AppShell";
import { ProtectedRoute } from "@/components/ProtectedRoute";
import { AdminConvites } from "@/pages/admin/AdminConvites";
import { AdminLicencas } from "@/pages/admin/AdminLicencas";
import { AdminPlanos } from "@/pages/admin/AdminPlanos";
import { AdminTenants } from "@/pages/admin/AdminTenants";
import { ConviteVitrine } from "@/pages/ConviteVitrine";
import { Dashboard } from "@/pages/Dashboard";
import { Login } from "@/pages/Login";
import { Aprovacoes } from "@/pages/aprovacoes/Aprovacoes";
import { Cadencias } from "@/pages/cadencias/Cadencias";
import { Configuracao } from "@/pages/configuracao/Configuracao";
import { Kanban } from "@/pages/crm/Kanban";
import { Map } from "@/pages/map/Map";
import { Prospeccao } from "@/pages/prospeccao/Prospeccao";
import { RedeSocial } from "@/pages/rede-social/RedeSocial";
import { Reunioes } from "@/pages/reunioes/Reunioes";

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/convite-vitrine/:codigo" element={<ConviteVitrine />} />

      <Route element={<ProtectedRoute />}>
        <Route element={<AppShell />}>
          <Route index element={<Dashboard />} />
          <Route path="crm" element={<Kanban />} />
          <Route path="rede-social" element={<RedeSocial />} />
          <Route path="map" element={<Map />} />
          <Route path="prospeccao" element={<Prospeccao />} />
          <Route path="cadencias" element={<Cadencias />} />
          <Route path="aprovacoes" element={<Aprovacoes />} />
          <Route path="reunioes" element={<Reunioes />} />
          <Route path="configuracao" element={<Configuracao />} />
          <Route path="admin/tenants" element={<AdminTenants />} />
          <Route path="admin/licencas" element={<AdminLicencas />} />
          <Route path="admin/convites" element={<AdminConvites />} />
          <Route path="admin/planos" element={<AdminPlanos />} />
        </Route>
      </Route>
    </Routes>
  );
}
