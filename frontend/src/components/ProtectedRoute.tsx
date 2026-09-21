import { Navigate, Outlet, useLocation } from "react-router-dom";

import { PaginaBoasVindas } from "@/pages/PaginaBoasVindas";
import { useAuth } from "@/lib/auth";

/** Raiz pública (raio-X 2026-09-21): visitante deslogado batendo
 * exatamente em `/` vê a página de boas-vindas, não é redirecionado pro
 * login — mas continua sendo a mesma rota `/` do Dashboard pra quem já
 * está autenticado (zero mudança de URL pra usuário existente). Deep
 * link pra qualquer outra rota protegida continua indo pro `/login`
 * normalmente. */
export function ProtectedRoute() {
  const { autenticado } = useAuth();
  const location = useLocation();
  if (!autenticado) {
    if (location.pathname === "/") return <PaginaBoasVindas />;
    return <Navigate to="/login" replace />;
  }
  return <Outlet />;
}
