import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { Badge } from "@/components/ui/Badge";
import { brl, creditos } from "@/lib/aiCredits";
import { api } from "@/lib/api";
import type { Catalogo, LinhaComercial, PlanoCatalogo } from "@/lib/catalogo";

const LADO: Record<LinhaComercial["lado"], string> = {
  SELL: "Para quem vende",
  BUY: "Para quem compra",
};

function PlanoDaLinha({
  plano,
  pendencias,
}: {
  plano: PlanoCatalogo;
  pendencias: string[];
}) {
  const aPartirDe = plano.tipo_preco === "STARTING_AT";
  return (
    <div
      className="flex flex-col gap-1 rounded-lg border border-border p-3"
      data-testid="plano-da-linha"
    >
      <div className="text-[12px] font-semibold text-text">{plano.nome}</div>
      <div className="font-head text-[16px] font-bold text-text">
        {aPartirDe && (
          <span className="text-[11px] font-normal text-muted">
            a partir de{" "}
          </span>
        )}
        {brl(plano.preco_mensal)}
        <span className="text-[11px] font-normal text-muted"> /mês</span>
      </div>
      <div className="text-[11px] text-muted">
        {creditos(plano.ai_credits_mensais)} de IA por mês
        {" · "}
        {plano.max_usuarios !== null
          ? `até ${plano.max_usuarios} usuários`
          : pendencias.includes("usuarios_incluidos")
            ? "usuários: a definir"
            : aPartirDe
              ? "usuários por contrato"
              : ""}
      </div>
      {plano.self_service ? (
        <Link
          to={`/criar-conta?plano=${encodeURIComponent(plano.nome)}`}
          className="mt-1 text-[12px] font-semibold text-cyan hover:underline"
        >
          Assinar →
        </Link>
      ) : (
        <a
          href={`mailto:comercial@cyberfort.com.br?subject=${encodeURIComponent(`Interesse: ${plano.nome}`)}`}
          className="mt-1 text-[12px] font-semibold text-cyan hover:underline"
        >
          Falar com o comercial →
        </a>
      )}
    </div>
  );
}

/** Produtos como são vendidos (Phase I, D-059), direto do `GET /catalogo`: preço, AI Credits e usuários vêm
 * dos planos do backend. O que o PO ainda não definiu aparece "em definição", nunca com número. */
export function LinhasComerciais() {
  const [linhas, setLinhas] = useState<LinhaComercial[] | null>(null);

  useEffect(() => {
    api
      .get<Catalogo>("/catalogo")
      .then((c) => setLinhas(c.linhas))
      .catch(() => setLinhas(null));
  }, []);

  if (!linhas) return null;
  return (
    <section data-testid="linhas-comerciais" className="mb-14">
      <div className="mb-6 text-center">
        <div className="text-[10px] font-semibold tracking-widest text-cyan uppercase">
          Produtos
        </div>
        <div className="mt-1.5 font-head text-xl font-bold text-text">
          Escolha pelo que você precisa fazer
        </div>
      </div>
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        {linhas.map((linha) => (
          <div
            key={linha.id}
            className="flex flex-col gap-2.5 rounded-xl border border-border bg-surf p-4.5"
            data-testid={`linha-${linha.id}`}
          >
            <div className="flex items-start justify-between gap-2">
              <span className="font-head text-[15px] font-bold text-text">
                {linha.nome}
              </span>
              <Badge tone={linha.lado === "BUY" ? "violet" : "cyan"}>
                {LADO[linha.lado]}
              </Badge>
            </div>
            <div className="text-[12px] leading-relaxed text-muted">
              {linha.descricao}
            </div>
            {linha.id === "revenue_intelligence" ? (
              <a
                href="#planos-suite"
                className="text-[12px] font-semibold text-cyan hover:underline"
              >
                Planos por usuário e por módulo abaixo ↓
              </a>
            ) : linha.planos.length > 0 ? (
              <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                {linha.planos.map((plano) => (
                  <PlanoDaLinha
                    key={plano.id}
                    plano={plano}
                    pendencias={linha.pendencias}
                  />
                ))}
              </div>
            ) : (
              <div className="flex flex-col gap-1">
                <Badge tone="muted">Preço em definição</Badge>
                <a
                  href={`mailto:comercial@cyberfort.com.br?subject=${encodeURIComponent(`Interesse: ${linha.nome}`)}`}
                  className="text-[12px] font-semibold text-cyan hover:underline"
                >
                  Quero ser avisado →
                </a>
              </div>
            )}
          </div>
        ))}
      </div>
    </section>
  );
}
