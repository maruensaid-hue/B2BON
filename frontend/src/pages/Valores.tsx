import { Link } from "react-router-dom";

import { SecaoAiCredits } from "@/components/SecaoAiCredits";

/** Menu "Valores" (área logada): os mesmos cards de AI Credits da página
 * pública de planos e valores, sem sair do app. */
export function Valores() {
  return (
    <div className="p-5.5">
      <div className="mb-2 flex flex-wrap items-end justify-between gap-2">
        <div>
          <div className="font-head text-xl font-bold">Valores</div>
          <div className="mt-0.5 text-[11px] text-muted">
            AI Credits incluídos, pacotes adicionais e quanto cada operação
            consome.
          </div>
        </div>
        <Link
          to="/planos"
          className="text-[12px] font-semibold text-cyan hover:underline"
        >
          Planos e valores da assinatura →
        </Link>
      </div>
      <SecaoAiCredits />
    </div>
  );
}
