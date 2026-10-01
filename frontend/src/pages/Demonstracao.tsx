import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { mensagemErro } from "@/lib/api";
import { useAuth } from "@/lib/auth";

/** Link público da demonstração (D-082): abre um ambiente próprio, já preenchido com dados fictícios, sem login nem
 * senha. Cada acesso é independente — vários representantes podem demonstrar ao mesmo tempo sem interferência. */
export function Demonstracao() {
  const { entrarDemonstracao } = useAuth();
  const navigate = useNavigate();
  const [erro, setErro] = useState<string | null>(null);
  const iniciado = useRef(false);

  useEffect(() => {
    if (iniciado.current) return;  // StrictMode monta duas vezes em desenvolvimento: uma sessão por acesso
    iniciado.current = true;
    entrarDemonstracao()
      .then(() => navigate("/", { replace: true }))
      .catch((e) => setErro(mensagemErro(e, "Não foi possível abrir a demonstração agora.")));
  }, [entrarDemonstracao, navigate]);

  return (
    <div className="flex min-h-screen items-center justify-center bg-bg p-6">
      <div className="max-w-md space-y-3 text-center">
        <div className="font-head text-[22px] font-bold text-text">B2B ON — demonstração</div>
        {erro ? (
          <>
            <div className="text-[13px] text-red">{erro}</div>
            <Link to="/login" className="text-[12px] text-cyan underline">Ir para o login</Link>
          </>
        ) : (
          <div className="text-[13px] text-muted">
            Preparando um ambiente só seu, com empresa, equipe, oportunidades, licitações e compras fictícias…
          </div>
        )}
      </div>
    </div>
  );
}
