import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { api } from "@/lib/api";
import { brl, creditos, type Franquia, type Pacote } from "@/lib/aiCredits";

const ROTULO_PRODUTO: Record<string, string> = {
  crm: "CRM",
  map: "MAP",
  predator: "PREDATOR",
  opportunity_intelligence: "Opportunity Intelligence",
  business_network: "Business Network Intelligence",
  bids: "Bid Intelligence",
  procurement: "Public Procurement",
  full_suite: "Suíte completa",
  enterprise: "Enterprise",
};

function franquiaTexto(franquia: Franquia): string {
  if (franquia.creditos !== null)
    return `+${creditos(franquia.creditos)} / mês${franquia.status === "ADDON" ? " (add-on)" : ""}`;
  if (franquia.status === "CUSTOM") return "Pool definido em contrato";
  return "Em definição";
}

/** Seção de vendas dos AI Credits: franquias por módulo e pacotes, tudo
 * lido da API (catálogo versionado). Usada na página de planos e na
 * explicação pública. */
export function SecaoAiCredits({
  comLinkExplicacao = true,
}: {
  comLinkExplicacao?: boolean;
}) {
  const [pacotes, setPacotes] = useState<Pacote[]>([]);
  const [franquias, setFranquias] = useState<Franquia[]>([]);
  const [erro, setErro] = useState(false);

  useEffect(() => {
    api
      .get<{ pacotes: Pacote[]; franquias: Franquia[] }>("/ai-credits/pacotes")
      .then((r) => {
        setPacotes(r.pacotes);
        setFranquias(r.franquias);
      })
      .catch(() => setErro(true));
  }, []);

  if (erro) return null;

  return (
    <section className="mt-14">
      <div className="mb-6 text-center">
        <div className="text-[10px] font-semibold tracking-widest text-cyan uppercase">
          B2B ON AI Credits
        </div>
        <div className="mt-1.5 font-head text-xl font-bold text-text">
          IA incluída no plano, com pacotes quando precisar de mais
        </div>
        <div className="mx-auto mt-1.5 max-w-2xl text-[12.5px] text-muted">
          Cada módulo contratado inclui AI Credits todo mês. Pacotes adicionais
          valem por 12 meses. Você vê o consumo estimado antes das operações
          maiores e define limites por módulo, usuário ou API.
          {comLinkExplicacao && (
            <>
              {" "}
              <Link
                to="/como-funcionam-ai-credits"
                className="text-cyan hover:underline"
              >
                Como funcionam os AI Credits
              </Link>
            </>
          )}
        </div>
      </div>

      <div className="mb-6 grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-5">
        {franquias
          .filter((f) => f.produto !== "full_suite")
          .map((franquia) => (
            <div
              key={franquia.produto}
              className="rounded-xl border border-border bg-surf p-3 text-[12px]"
            >
              <div className="font-bold text-text">
                {ROTULO_PRODUTO[franquia.produto] ?? franquia.produto}
              </div>
              <div className="text-muted">{franquiaTexto(franquia)}</div>
            </div>
          ))}
      </div>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {pacotes.map((pacote) => (
          <div
            key={pacote.codigo}
            className="flex flex-col gap-1 rounded-2xl border border-border bg-surf p-4"
          >
            <div className="text-[11px] font-bold tracking-wide text-muted uppercase">
              {pacote.nome}
            </div>
            {pacote.status === "CONTACT_SALES" ? (
              <>
                <div className="font-head text-[18px] font-bold text-text">
                  Sob medida
                </div>
                <a
                  href="mailto:comercial@cyberfort.com.br?subject=AI%20Credits%20Enterprise"
                  className="mt-auto text-[12px] font-semibold text-cyan hover:underline"
                >
                  Falar com vendas
                </a>
              </>
            ) : (
              <>
                <div className="text-[12.5px] text-text">
                  {creditos(pacote.creditos ?? 0)}
                </div>
                <div className="font-head text-[22px] font-extrabold text-text">
                  {brl(pacote.preco ?? 0)}
                </div>
                {pacote.preco_efetivo_por_1000 !== null && (
                  <div className="text-[11px] text-muted">
                    {brl(pacote.preco_efetivo_por_1000)} por 1.000 créditos
                  </div>
                )}
              </>
            )}
          </div>
        ))}
      </div>
    </section>
  );
}
