import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { api } from "@/lib/api";

type Status = "verificando" | "ativa" | "pendente_pagamento" | "demorando" | "erro";

const INTERVALO_MS = 3000;
const TENTATIVAS_MAXIMAS = 40; // ~2 minutos

export function PagamentoRetorno() {
  const navigate = useNavigate();
  const [status, setStatus] = useState<Status>("verificando");
  const tentativas = useRef(0);

  useEffect(() => {
    let cancelado = false;

    async function verificar() {
      try {
        const resposta = await api.get<{ status: string }>("/auth/licenca-status");
        if (cancelado) return;

        if (resposta.status === "ativa") {
          setStatus("ativa");
          setTimeout(() => navigate("/", { replace: true }), 1500);
          return;
        }

        tentativas.current += 1;
        if (tentativas.current >= TENTATIVAS_MAXIMAS) {
          setStatus("demorando");
          return;
        }
        setStatus("pendente_pagamento");
        setTimeout(verificar, INTERVALO_MS);
      } catch {
        if (!cancelado) setStatus("erro");
      }
    }

    verificar();
    return () => {
      cancelado = true;
    };
  }, [navigate]);

  return (
    <div className="flex min-h-screen items-center justify-center p-4">
      <Card glow className="w-full max-w-sm text-center">
        {status === "verificando" && (
          <>
            <div className="font-head text-lg font-bold">Confirmando seu pagamento...</div>
            <div className="mt-2 text-[12px] text-muted">Só um instante.</div>
          </>
        )}
        {status === "pendente_pagamento" && (
          <>
            <div className="font-head text-lg font-bold">Ainda processando...</div>
            <div className="mt-2 text-[12px] text-muted">
              O Mercado Pago está confirmando seu pagamento. Isso costuma levar só alguns segundos.
            </div>
          </>
        )}
        {status === "ativa" && (
          <>
            <div className="font-head text-lg font-bold text-green">Pagamento aprovado!</div>
            <div className="mt-2 text-[12px] text-muted">Redirecionando para a plataforma...</div>
          </>
        )}
        {status === "demorando" && (
          <>
            <div className="font-head text-lg font-bold">Está demorando mais que o esperado</div>
            <div className="mt-2 text-[12px] text-muted">
              Se você concluiu o pagamento, ele pode ainda estar sendo processado — você pode fechar esta página e
              conferir mais tarde fazendo login normalmente.
            </div>
            <Button className="mt-4 w-full justify-center" onClick={() => navigate("/login")}>
              Ir para o login
            </Button>
          </>
        )}
        {status === "erro" && (
          <>
            <div className="font-head text-lg font-bold text-red">Não foi possível verificar o pagamento</div>
            <div className="mt-2 text-[12px] text-muted">
              Faça login para conferir o status da sua conta.
            </div>
            <Button className="mt-4 w-full justify-center" onClick={() => navigate("/login")}>
              Ir para o login
            </Button>
          </>
        )}
      </Card>
    </div>
  );
}
