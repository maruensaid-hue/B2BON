import { Link } from "react-router-dom";

import { SecaoAiCredits } from "@/components/SecaoAiCredits";

/** Página pública "Como funcionam os AI Credits" (Fase 15). Todo o
 * conteúdo em cards vem de `SecaoAiCredits` (dados da API). */
export function ComoFuncionamAiCredits() {
  return (
    <div className="min-h-screen bg-bg text-text">
      <header className="border-b border-border px-5 py-4">
        <Link to="/planos" className="font-head text-[15px] font-bold">
          B2B ON
        </Link>
      </header>
      <main className="mx-auto max-w-5xl px-5 py-10">
        <h1 className="font-head text-2xl font-bold">
          Como funcionam os AI Credits
        </h1>
        <p className="mt-2 max-w-3xl text-[13px] text-muted">
          Os créditos vêm do seu plano todo mês e de pacotes adicionais. O
          consumo aparece por módulo, operação, agente e usuário.
        </p>
        <SecaoAiCredits comLinkExplicacao={false} />
        <div className="mt-10 text-center">
          <Link
            to="/planos"
            className="text-[13px] font-semibold text-cyan hover:underline"
          >
            Ver planos e valores
          </Link>
        </div>
      </main>
    </div>
  );
}
