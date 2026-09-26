import { useEffect, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";

import { api } from "@/lib/api";
import { brl, creditos, type Franquia, type Pacote } from "@/lib/aiCredits";

interface Workload {
  codigo: string;
  modulo: string;
  nome: string;
  creditos_base: number;
  creditos_min: number | null;
  creditos_max: number | null;
  requer_aprovacao: boolean;
}

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

const ROTULO_MODULO: Record<string, string> = {
  predator: "PREDATOR",
  crm: "CRM",
  map: "MAP",
  bids: "Licitações",
  procurement: "Compras públicas",
  intelligence: "Inteligência",
  network: "Rede de negócios",
  plataforma: "Plataforma",
};

const ORDEM_MODULOS = [
  "crm",
  "map",
  "predator",
  "intelligence",
  "network",
  "bids",
  "procurement",
  "plataforma",
];

const PERGUNTAS_AI_CREDITS: {
  icone: string;
  pergunta: string;
  resposta: string;
}[] = [
  {
    icone: "💠",
    pergunta: "O que é um AI Credit?",
    resposta:
      "É a unidade de consumo das funções de inteligência artificial da B2B ON. Cada operação consome um número fixo de créditos, conforme a complexidade: uma classificação simples consome 1, uma análise de edital consome 50.",
  },
  {
    icone: "📅",
    pergunta: "Os créditos do plano acumulam?",
    resposta:
      "Não. Os créditos incluídos no plano são mensais e vencem no fim do mês. Os créditos comprados valem por 12 meses.",
  },
  {
    icone: "⏳",
    pergunta: "Qual crédito é usado primeiro?",
    resposta:
      "O que vence primeiro. Assim, créditos promocionais e os do mês são consumidos antes dos comprados, que duram mais.",
  },
  {
    icone: "🔍",
    pergunta: "Vou ser surpreendido por uma operação cara?",
    resposta:
      "Não. Operações maiores, como a análise de um documento longo, mostram o consumo estimado e só rodam depois da sua confirmação.",
  },
  {
    icone: "🛡️",
    pergunta: "E se a IA falhar?",
    resposta:
      "Se a operação falhar por problema do provedor ou do sistema, os créditos não são cobrados.",
  },
  {
    icone: "🎚️",
    pergunta: "Como controlo o consumo?",
    resposta:
      "O administrador define limites por mês, por dia, por usuário, por módulo (por exemplo, PREDATOR até 40%) e para a API, e recebe avisos em 80%, 95% e 100% do uso.",
  },
  {
    icone: "🔁",
    pergunta: "Posso recarregar automaticamente?",
    resposta:
      "Sim, só com o seu consentimento: quando o saldo ficar abaixo do limite escolhido, criamos o pedido do pacote e avisamos o administrador.",
  },
];

function franquiaTexto(franquia: Franquia): string {
  if (franquia.creditos !== null)
    return `+${creditos(franquia.creditos)} / mês${franquia.status === "ADDON" ? " (add-on)" : ""}`;
  if (franquia.status === "CUSTOM") return "Pool definido em contrato";
  return "Em definição";
}

function consumoTexto(w: Workload): string {
  if (
    w.creditos_min !== null &&
    w.creditos_max !== null &&
    w.creditos_min !== w.creditos_max
  )
    return `${w.creditos_min}–${w.creditos_max}`;
  return String(w.creditos_base);
}

function Bloco({
  titulo,
  subtitulo,
  children,
}: {
  titulo: string;
  subtitulo?: string;
  children: ReactNode;
}) {
  return (
    <div className="mt-8">
      <div className="mb-3">
        <div className="font-head text-[15px] font-bold text-text">
          {titulo}
        </div>
        {subtitulo && (
          <div className="mt-0.5 text-[12px] text-muted">{subtitulo}</div>
        )}
      </div>
      {children}
    </div>
  );
}

/** B2B ON AI Credits em cards: como funciona, créditos incluídos por
 * módulo, pacotes adicionais e consumo por operação. Preços, franquias e
 * pesos vêm da API (catálogo versionado); nada fixo no código. Usada na
 * página de planos e valores, na explicação pública e no menu Valores. */
export function SecaoAiCredits({
  comLinkExplicacao = true,
}: {
  comLinkExplicacao?: boolean;
}) {
  const [pacotes, setPacotes] = useState<Pacote[]>([]);
  const [franquias, setFranquias] = useState<Franquia[]>([]);
  const [workloads, setWorkloads] = useState<Workload[]>([]);
  const [erro, setErro] = useState(false);

  useEffect(() => {
    api
      .get<{ pacotes: Pacote[]; franquias: Franquia[] }>("/ai-credits/pacotes")
      .then((r) => {
        setPacotes(r.pacotes);
        setFranquias(r.franquias);
      })
      .catch(() => setErro(true));
    api
      .get<{ workloads: Workload[] }>("/ai-credits/workloads")
      .then((r) => setWorkloads(r.workloads.filter((w) => w.creditos_base > 0)))
      .catch(() => setWorkloads([]));
  }, []);

  if (erro) return null;

  const porModulo = ORDEM_MODULOS.map((modulo) => ({
    modulo,
    itens: workloads.filter((w) => w.modulo === modulo),
  })).filter((grupo) => grupo.itens.length > 0);

  return (
    <section className="mt-14" data-testid="ai-credits-cards">
      <div className="mb-2 text-center">
        <div className="text-[10px] font-semibold tracking-widest text-cyan uppercase">
          B2B ON AI Credits
        </div>
        <div className="mt-1.5 font-head text-xl font-bold text-text">
          IA incluída no plano, com pacotes quando precisar de mais
        </div>
        <div className="mx-auto mt-1.5 max-w-2xl text-[12.5px] text-muted">
          Uma carteira de créditos por empresa, compartilhada por todos os
          usuários e módulos.
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

      <Bloco titulo="Como funciona">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {PERGUNTAS_AI_CREDITS.map((item) => (
            <div
              key={item.pergunta}
              className="rounded-xl border border-border bg-surf p-4"
            >
              <div className="text-lg">{item.icone}</div>
              <div className="mt-1.5 text-[13px] font-bold text-text">
                {item.pergunta}
              </div>
              <div className="mt-1 text-[12px] leading-relaxed text-muted">
                {item.resposta}
              </div>
            </div>
          ))}
        </div>
      </Bloco>

      <Bloco
        titulo="Créditos incluídos todo mês"
        subtitulo="Por módulo contratado. Não acumulam para o mês seguinte."
      >
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
          {franquias
            .filter((f) => f.produto !== "full_suite")
            .map((franquia) => (
              <div
                key={franquia.produto}
                className="rounded-xl border border-border bg-surf p-4"
              >
                <div className="text-[13px] font-bold text-text">
                  {ROTULO_PRODUTO[franquia.produto] ?? franquia.produto}
                </div>
                <div
                  className={`mt-1 text-[12.5px] ${franquia.creditos !== null ? "text-cyan" : "text-muted"}`}
                >
                  {franquiaTexto(franquia)}
                </div>
              </div>
            ))}
        </div>
      </Bloco>

      <Bloco
        titulo="Pacotes adicionais"
        subtitulo="Créditos comprados valem por 12 meses."
      >
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
      </Bloco>

      {porModulo.length > 0 && (
        <Bloco
          titulo="Quanto cada operação consome"
          subtitulo="Créditos por operação, conforme a complexidade."
        >
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {porModulo.map((grupo) => (
              <div
                key={grupo.modulo}
                className="rounded-xl border border-border bg-surf p-4"
              >
                <div className="mb-2 text-[13px] font-bold text-text">
                  {ROTULO_MODULO[grupo.modulo] ?? grupo.modulo}
                </div>
                {grupo.itens.map((w) => (
                  <div
                    key={w.codigo}
                    className="flex justify-between gap-2 border-t border-border py-1.5 text-[12px]"
                  >
                    <span className="text-muted">
                      {w.nome}
                      {w.requer_aprovacao && <span> · pede confirmação</span>}
                    </span>
                    <span className="shrink-0 font-semibold text-text">
                      {consumoTexto(w)}
                    </span>
                  </div>
                ))}
              </div>
            ))}
          </div>
        </Bloco>
      )}
    </section>
  );
}
