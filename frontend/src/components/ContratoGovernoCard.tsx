import { Badge } from "@/components/ui/Badge";
import { Card, SectionLabel } from "@/components/ui/Card";
import { brl } from "@/lib/aiCredits";
import {
  data,
  ROTULO_COMPONENTE,
  ROTULO_MODELO,
  type ContratoGoverno,
} from "@/lib/governo";

/** Contrato governamental na área do cliente (D-072): componentes separados, período anual, renovação e pool de
 * AI Credits do período. Sem comissões. */
export function ContratoGovernoCard({
  contrato,
}: {
  contrato: ContratoGoverno;
}) {
  const atual =
    contrato.periodos.find((p) => p.status === "ATIVO") ??
    contrato.periodos[contrato.periodos.length - 1];
  const pool = atual?.creditos;
  return (
    <Card data-testid="contrato-governo">
      <SectionLabel>Contrato governamental</SectionLabel>
      <div className="flex flex-col gap-1.5 text-[12px]">
        <div className="font-semibold text-text">
          {contrato.referencia_contrato} · {contrato.entidade_governamental}
        </div>
        <div className="text-muted">
          {ROTULO_MODELO[contrato.modelo_cobranca] ?? contrato.modelo_cobranca}{" "}
          · assinado em {data(contrato.assinado_em)}
        </div>
        <div className="mt-1 flex flex-col gap-1 border-t border-dashed border-border2 pt-2">
          {contrato.componentes
            .filter((c) => !c.cancelado)
            .map((c) => (
              <div key={c.id} className="flex justify-between gap-2">
                <span className="text-muted">
                  {ROTULO_COMPONENTE[c.tipo] ?? c.tipo}
                </span>
                <span>
                  {brl(c.valor)}{" "}
                  <span className="text-[10px] text-muted">
                    · recebido {brl(c.recebido)}
                  </span>
                </span>
              </div>
            ))}
        </div>
        {atual && (
          <div className="mt-1 border-t border-dashed border-border2 pt-2">
            Período {atual.numero} ({data(atual.inicio)} a {data(atual.fim)}) ·
            renovação em {data(atual.data_renovacao)}{" "}
            <Badge
              tone={atual.status_renovacao === "NOTIFICADA" ? "amber" : "muted"}
            >
              {atual.status_renovacao}
            </Badge>
            <div className="text-muted">
              Renovação: {brl(atual.valor_assinatura)}/ano, sujeita às condições
              contratuais.
            </div>
          </div>
        )}
        {pool && (
          <div
            className="mt-1 border-t border-dashed border-border2 pt-2"
            data-testid="pool-anual"
          >
            AI Credits do período:{" "}
            {pool.credits_remaining.toLocaleString("pt-BR")} de{" "}
            {pool.annual_credit_pool.toLocaleString("pt-BR")} disponíveis (
            {pool.credits_consumed.toLocaleString("pt-BR")} usados) · válidos
            até {data(pool.valid_until)}
          </div>
        )}
      </div>
    </Card>
  );
}
