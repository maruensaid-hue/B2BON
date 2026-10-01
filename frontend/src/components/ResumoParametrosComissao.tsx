import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { Card, SectionLabel } from "@/components/ui/Card";
import { api } from "@/lib/api";

/** D-074: lembrete de que toda comissão é calculada sobre a Margem Comissionável Líquida e de quantas aguardam os
 * parâmetros de custo (Tax Profile e Infrastructure Cost Model). */
export function ResumoParametrosComissao() {
  const [aguardando, setAguardando] = useState<number | null>(null);

  useEffect(() => {
    api
      .get<unknown[]>("/comissoes/apuracoes?status=AWAITING_COST_PARAMETERS")
      .then((lista) => setAguardando(lista.length))
      .catch(() => setAguardando(null));
  }, []);

  return (
    <Card data-testid="resumo-parametros-comissao">
      <SectionLabel>
        Base das comissões — Margem Comissionável Líquida
      </SectionLabel>
      <div className="text-[12px] text-muted">
        Comissão = (receita recebida − impostos atribuíveis − infraestrutura
        atribuível) × taxa.{" "}
        {aguardando ? (
          <span className="text-amber">
            {aguardando} recebimento(s) aguardando parâmetros de custo —
            comissões sem valor até lá.
          </span>
        ) : null}{" "}
        <Link
          to="/admin/parametros-financeiros"
          className="font-semibold text-cyan hover:underline"
        >
          Parâmetros financeiros →
        </Link>
      </div>
    </Card>
  );
}
