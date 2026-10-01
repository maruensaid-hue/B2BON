import { useNavigate } from "react-router-dom";

import { getDemoExpiraEm } from "@/lib/api";
import { useAuth } from "@/lib/auth";

/** Aviso fixo no topo de toda sessão de demonstração (D-082): dados fictícios, nada é enviado de verdade e o ambiente
 * expira sozinho. "Nova demonstração" abre outro ambiente limpo. */
export function FaixaDemonstracao() {
  const { sair } = useAuth();
  const navigate = useNavigate();
  const expiraEm = getDemoExpiraEm();
  if (!expiraEm) return null;
  const hora = new Date(expiraEm.endsWith("Z") ? expiraEm : `${expiraEm}Z`).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
  return (
    <div className="flex flex-wrap items-center gap-2 border-b border-amber/30 bg-amber/10 px-4 py-2 text-[12px] text-amber">
      <span className="font-semibold">Ambiente de demonstração</span>
      <span>— empresa e dados fictícios; e-mails e WhatsApp são simulados (nada sai de verdade). Expira às {hora}.</span>
      <button type="button" className="ml-auto underline"
        onClick={() => { sair(); navigate("/demo", { replace: true }); }}>Nova demonstração</button>
    </div>
  );
}
