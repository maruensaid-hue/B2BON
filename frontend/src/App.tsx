import { Route, Routes } from "react-router-dom";

import { AppShell } from "@/components/AppShell";
import { ProtectedRoute } from "@/components/ProtectedRoute";
import { Dashboard } from "@/pages/Dashboard";
import { Login } from "@/pages/Login";
import { Kanban } from "@/pages/crm/Kanban";
import { EmConstrucao } from "@/pages/placeholder/EmConstrucao";

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />

      <Route element={<ProtectedRoute />}>
        <Route element={<AppShell />}>
          <Route index element={<Dashboard />} />
          <Route path="crm" element={<Kanban />} />
          <Route path="rede-social" element={<EmConstrucao titulo="Rede Social" />} />
          <Route path="map" element={<EmConstrucao titulo="MAP — Motor de Alta Performance" />} />
          <Route path="prospeccao" element={<EmConstrucao titulo="Prospecção (PREDATOR)" />} />
          <Route path="admin/tenants" element={<EmConstrucao titulo="Admin — Tenants" />} />
          <Route path="admin/licencas" element={<EmConstrucao titulo="Admin — Licenças" />} />
          <Route path="admin/convites" element={<EmConstrucao titulo="Admin — Convites" />} />
          <Route path="admin/planos" element={<EmConstrucao titulo="Admin — Planos" />} />
        </Route>
      </Route>
    </Routes>
  );
}
