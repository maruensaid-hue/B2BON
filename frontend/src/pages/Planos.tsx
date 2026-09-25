import { Link } from "react-router-dom";

import { CatalogoProdutos } from "@/components/CatalogoProdutos";
import { SecaoAiCredits } from "@/components/SecaoAiCredits";

interface Modulo {
  nome: string;
  descricao: string;
  precoLabel: string;
  gratuito?: boolean;
}

const MODULOS: Modulo[] = [
  {
    nome: "Shoal",
    descricao:
      "Rede social B2B entre empresas parceiras, fornecedoras e clientes: perfil, diretório, conexões e mensagens diretas.",
    precoLabel: "Acesso gratuito",
    gratuito: true,
  },
  {
    nome: "MAP",
    descricao:
      "Saúde da carteira de contas: score de risco, ranking de saúde, alertas de churn e roteiro de resgate gerado por IA.",
    precoLabel: "R$ 29,90 / usuário / mês",
  },
  {
    nome: "PREDATOR",
    descricao:
      "Motor de prospecção com IA: da geração de listas de contas até a reunião qualificada, sempre com aprovação humana antes de qualquer envio.",
    precoLabel: "R$ 95,10 / usuário / mês",
  },
  {
    nome: "CRM",
    descricao: "Funil de vendas em Kanban: pipeline, negócios, atividades e o dashboard de performance do time comercial.",
    precoLabel: "R$ 59,90 / usuário / mês",
  },
];

interface TierModulo {
  nome: string;
  usuarios: string;
  preco: string;
  /** Ausente = "On Demand" avulso, sem Plano de checkout (preço varia
   * por assento) — mesmo padrão do "On Demand" da suíte completa. */
  checkoutPlanoNome?: string;
}

interface ModuloContratacao {
  nome: string;
  tiers: TierModulo[];
}

// Contratação avulsa por módulo (raio-X 2026-09-22, checkout self-service
// real desde 2026-09-24) — pra quem não quer a suíte inteira. Reaproveita
// os mesmos valores já validados na contratação da suíte completa (é a
// mesma linha de cada módulo dentro de cada faixa de `PLANOS` abaixo, só
// apresentada separada). `checkoutPlanoNome` bate com o nome dos 9 novos
// `Plano`s avulsos (migração `807d7076f1df`). Shoal fica de fora — é
// sempre gratuito, não é vendido avulso.
const CONTRATACAO_POR_MODULO: ModuloContratacao[] = [
  {
    nome: "MAP",
    tiers: [
      { nome: "Starter", usuarios: "Até 5 usuários", preco: "R$ 149,50/mês", checkoutPlanoNome: "MAP Starter" },
      {
        nome: "Professional",
        usuarios: "Até 10 usuários",
        preco: "R$ 269,10/mês",
        checkoutPlanoNome: "MAP Professional",
      },
      {
        nome: "Enterprise",
        usuarios: "Até 20 usuários",
        preco: "R$ 478,40/mês",
        checkoutPlanoNome: "MAP Enterprise",
      },
      { nome: "On Demand", usuarios: "Acima de 20 usuários", preco: "R$ 20,90/usuário/mês" },
    ],
  },
  {
    nome: "PREDATOR",
    tiers: [
      {
        nome: "Starter",
        usuarios: "Até 5 usuários",
        preco: "R$ 475,50/mês",
        checkoutPlanoNome: "PREDATOR Starter",
      },
      {
        nome: "Professional",
        usuarios: "Até 10 usuários",
        preco: "R$ 855,90/mês",
        checkoutPlanoNome: "PREDATOR Professional",
      },
      {
        nome: "Enterprise",
        usuarios: "Até 20 usuários",
        preco: "R$ 1.521,60/mês",
        checkoutPlanoNome: "PREDATOR Enterprise",
      },
      { nome: "On Demand", usuarios: "Acima de 20 usuários", preco: "R$ 66,90/usuário/mês" },
    ],
  },
  {
    nome: "CRM",
    tiers: [
      { nome: "Starter", usuarios: "Até 5 usuários", preco: "R$ 299,50/mês", checkoutPlanoNome: "CRM Starter" },
      {
        nome: "Professional",
        usuarios: "Até 10 usuários",
        preco: "R$ 539,10/mês",
        checkoutPlanoNome: "CRM Professional",
      },
      {
        nome: "Enterprise",
        usuarios: "Até 20 usuários",
        preco: "R$ 958,40/mês",
        checkoutPlanoNome: "CRM Enterprise",
      },
      { nome: "On Demand", usuarios: "Acima de 20 usuários", preco: "R$ 41,90/usuário/mês" },
    ],
  },
];

interface Plano {
  nome: string;
  usuarios: string;
  total: string;
  porUsuario: string;
  destaque?: boolean;
  linhas: { nome: string; valor: string }[];
  /** Ausente = ainda não existe como Plano self-service (caso do "On
   * Demand", cujo preço varia por assento) — o card oferece falar com o
   * comercial em vez de ir direto pro checkout. */
  checkoutPlanoNome?: string;
}

const PLANOS: Plano[] = [
  {
    nome: "Starter",
    usuarios: "Até 5 usuários",
    total: "R$ 924,50",
    porUsuario: "R$ 184,90 por usuário",
    checkoutPlanoNome: "Starter",
    linhas: [
      { nome: "Rede social", valor: "Grátis" },
      { nome: "MAP", valor: "R$ 149,50" },
      { nome: "PREDATOR", valor: "R$ 475,50" },
      { nome: "CRM", valor: "R$ 299,50" },
    ],
  },
  {
    nome: "Professional",
    usuarios: "Até 10 usuários",
    total: "R$ 1.664,10",
    porUsuario: "R$ 166,41 por usuário · 10% de desconto",
    destaque: true,
    checkoutPlanoNome: "Professional",
    linhas: [
      { nome: "Rede social", valor: "Grátis" },
      { nome: "MAP", valor: "R$ 269,10" },
      { nome: "PREDATOR", valor: "R$ 855,90" },
      { nome: "CRM", valor: "R$ 539,10" },
    ],
  },
  {
    nome: "Enterprise",
    usuarios: "Até 20 usuários",
    total: "R$ 2.958,40",
    porUsuario: "R$ 147,92 por usuário · 20% de desconto",
    checkoutPlanoNome: "Enterprise",
    linhas: [
      { nome: "Rede social", valor: "Grátis" },
      { nome: "MAP", valor: "R$ 478,40" },
      { nome: "PREDATOR", valor: "R$ 1.521,60" },
      { nome: "CRM", valor: "R$ 958,40" },
    ],
  },
  {
    nome: "On Demand",
    usuarios: "Acima de 20 usuários",
    total: "R$ 129,70",
    porUsuario: "por usuário / mês",
    linhas: [
      { nome: "Rede social", valor: "Grátis" },
      { nome: "MAP", valor: "R$ 20,90" },
      { nome: "PREDATOR", valor: "R$ 66,90" },
      { nome: "CRM", valor: "R$ 41,90" },
    ],
  },
];

/** Página pública de planos e valores (raio-X 2026-09-22) — acessível a
 * partir do botão "Planos e Valores" da página de boas-vindas, sem
 * exigir login. Preço por módulo (Shoal grátis, MAP/PREDATOR/CRM pagos)
 * e preço da suíte completa por faixa de usuários, com desconto
 * progressivo (Starter 0%, Professional 10%, Enterprise 20%, On Demand
 * ~30%) — mesma lógica da planilha comercial validada com o usuário. */
export function Planos() {
  return (
    <div className="min-h-screen bg-bg">
      <header className="border-b border-nav-border bg-nav-bg">
        <div className="mx-auto flex max-w-5xl items-center justify-between px-5.5 py-4">
          <Link to="/" className="flex items-center gap-2.5">
            <div className="flex h-8.5 w-8.5 flex-shrink-0 items-center justify-center rounded-lg bg-gradient-to-br from-cyan to-[#005F7A] font-head text-[17px] font-black text-white">
              B
            </div>
            <div className="font-head text-[15px] font-extrabold text-nav-text">
              B2B <span className="text-cyan">ON</span>
            </div>
          </Link>
          <Link to="/login" className="text-[12.5px] font-semibold text-nav-muted hover:text-nav-text">
            Fazer login
          </Link>
        </div>

        <div className="mx-auto max-w-3xl px-5.5 pt-8 pb-14 text-center">
          <div className="text-[10px] font-semibold tracking-widest text-cyan uppercase">Planos e valores</div>
          <h1 className="mt-2 font-head text-[26px] leading-tight font-black text-nav-text sm:text-[32px]">
            Um preço por usuário. Quatro módulos trabalhando juntos.
          </h1>
          <p className="mt-3 text-[13.5px] leading-relaxed text-nav-muted">
            Rede social, inteligência de contas, prospecção com IA e CRM — na mesma licença, com
            desconto progressivo conforme o time cresce.
          </p>
        </div>
      </header>

      <main className="mx-auto max-w-5xl px-5.5 py-12">
        {/* Campanha especial de lançamento */}
        <div className="mb-12 flex flex-col items-center gap-1.5 rounded-2xl border border-amber/30 bg-amber/10 px-6 py-5 text-center">
          <div className="text-[10px] font-bold tracking-widest text-amber uppercase">
            🎉 Campanha especial de lançamento
          </div>
          <div className="font-head text-[17px] font-extrabold text-text sm:text-[19px]">
            Na assinatura do CRM, o MAP é sem custo!
          </div>
        </div>

        <div className="mb-8 text-center">
          <div className="text-[10px] font-semibold tracking-widest text-cyan uppercase">O que compõe a licença</div>
          <div className="mt-1.5 font-head text-xl font-bold text-text">Módulos</div>
        </div>

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {MODULOS.map((modulo) => (
            <div key={modulo.nome} className="flex flex-col gap-2.5 rounded-xl border border-border bg-surf p-4.5">
              <div className="font-head text-[15px] font-bold text-text">{modulo.nome}</div>
              <div className="flex-1 text-[12px] leading-relaxed text-muted">{modulo.descricao}</div>
              <div
                className={`border-t border-dashed border-border2 pt-2.5 font-head text-[13.5px] font-bold ${
                  modulo.gratuito ? "text-green" : "text-text"
                }`}
              >
                {modulo.precoLabel}
              </div>
            </div>
          ))}
        </div>

        <div className="mt-14 mb-8 text-center">
          <div className="text-[10px] font-semibold tracking-widest text-cyan uppercase">Ou contrate separado</div>
          <div className="mt-1.5 font-head text-xl font-bold text-text">Contratação por módulo</div>
          <div className="mx-auto mt-2 max-w-lg text-[12px] text-muted">
            Precisa só de um módulo? MAP, PREDATOR e CRM também podem ser contratados avulsos, na
            mesma faixa de desconto por usuário da suíte completa. Shoal é sempre gratuito, com ou
            sem outro módulo contratado.
          </div>
        </div>

        <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
          {CONTRATACAO_POR_MODULO.map((modulo) => (
            <div key={modulo.nome} className="flex flex-col gap-3 rounded-xl border border-border bg-surf p-4.5">
              <div className="font-head text-[15px] font-bold text-text">{modulo.nome}</div>
              <div className="flex flex-col gap-2.5 border-t border-border pt-3">
                {modulo.tiers.map((tier) => (
                  <div key={tier.nome} className="flex items-baseline justify-between gap-2 text-[12px]">
                    <div>
                      <div className="font-semibold text-text">{tier.nome}</div>
                      <div className="text-[10.5px] text-muted">{tier.usuarios}</div>
                    </div>
                    <div className="flex-shrink-0 text-right">
                      <div className="font-head text-[12.5px] font-bold text-cyan">{tier.preco}</div>
                      {tier.checkoutPlanoNome && (
                        <Link
                          to={`/criar-conta?plano=${encodeURIComponent(tier.checkoutPlanoNome)}`}
                          className="text-[10px] font-semibold text-cyan hover:underline"
                        >
                          Assinar →
                        </Link>
                      )}
                    </div>
                  </div>
                ))}
              </div>
              <div className="border-t border-dashed border-border2 pt-2.5 text-[10.5px] text-muted">
                Acima de 100 usuários: condições negociadas com o comercial.
              </div>
              <a
                href={`mailto:comercial@cyberfort.com.br?subject=${encodeURIComponent(
                  `Contratação avulsa: ${modulo.nome} — On Demand / acima de 100 usuários`,
                )}`}
                className="mt-1 rounded-lg border border-border px-4 py-2.5 text-center text-[13px] font-bold text-text transition-colors hover:bg-surf2"
              >
                Falar com o comercial (On Demand / +100 usuários)
              </a>
            </div>
          ))}
        </div>

        <div className="mt-14 mb-8 text-center">
          <div className="text-[10px] font-semibold tracking-widest text-cyan uppercase">Preço da suíte completa</div>
          <div className="mt-1.5 font-head text-xl font-bold text-text">Planos por número de usuários</div>
        </div>

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {PLANOS.map((plano) => (
            <div
              key={plano.nome}
              className={`relative flex flex-col gap-4 rounded-2xl border bg-surf p-5 ${
                plano.destaque ? "border-cyan shadow-[0_0_0_1px_var(--color-cyan)]" : "border-border"
              }`}
            >
              {plano.destaque && (
                <span className="absolute -top-2.5 left-5 rounded-full bg-cyan px-2.5 py-0.5 text-[10px] font-bold text-white">
                  Mais escolhido
                </span>
              )}
              <div>
                <div className="text-[11px] font-bold tracking-wide text-muted uppercase">{plano.nome}</div>
                <div className="text-[12px] text-muted">{plano.usuarios}</div>
              </div>
              <div className="flex items-baseline gap-1.5">
                <span className="font-head text-[26px] font-extrabold text-text">{plano.total}</span>
                <span className="text-[11px] text-muted">{plano.nome === "On Demand" ? "" : "/ mês"}</span>
              </div>
              <div className="flex flex-col gap-2 border-t border-border pt-3">
                {plano.linhas.map((linha) => (
                  <div key={linha.nome} className="flex justify-between text-[12.5px]">
                    <span className="text-muted">{linha.nome}</span>
                    <span className={`font-semibold ${linha.valor === "Grátis" ? "text-green" : "text-text"}`}>
                      {linha.valor}
                    </span>
                  </div>
                ))}
              </div>
              <div className="text-[11px] text-muted">{plano.porUsuario}</div>
              {plano.checkoutPlanoNome ? (
                <Link
                  to={`/criar-conta?plano=${encodeURIComponent(plano.checkoutPlanoNome)}`}
                  className={`mt-1 rounded-lg px-4 py-2.5 text-center text-[13px] font-bold transition-transform hover:scale-[1.02] ${
                    plano.destaque ? "bg-cyan text-white" : "border border-border text-text hover:bg-surf2"
                  }`}
                >
                  Assine aqui
                </Link>
              ) : (
                <a
                  href="mailto:comercial@cyberfort.com.br?subject=Plano%20On%20Demand%20B2B%20ON"
                  className="mt-1 rounded-lg border border-border px-4 py-2.5 text-center text-[13px] font-bold text-text transition-colors hover:bg-surf2"
                >
                  Falar com o comercial
                </a>
              )}
            </div>
          ))}
        </div>

        <div className="mt-6 rounded-xl border border-border bg-surf2 px-5 py-4 text-center text-[12.5px] text-muted">
          <strong className="text-text">Acima de 100 usuários</strong> — condições negociadas com o time comercial da
          B2B ON.
        </div>

        <SecaoAiCredits />

        <CatalogoProdutos />

        <div className="mt-12 rounded-2xl border border-border2 bg-surf p-7 text-center shadow-[0_0_20px_rgba(0,194,255,0.06)]">
          <div className="font-head text-lg font-bold text-text">Pronto pra ver a diferença?</div>
          <div className="mt-1.5 text-[12.5px] text-muted">
            Crie sua conta agora e escolha o plano que faz sentido pro tamanho do seu time.
          </div>
          <Link
            to="/criar-conta"
            className="mt-4 inline-block rounded-lg bg-cyan px-6 py-3 text-[13.5px] font-bold text-white transition-transform hover:scale-[1.02]"
          >
            Comece a usar gratuitamente
          </Link>
        </div>
      </main>

      <footer className="border-t border-border py-5 text-center text-[10.5px] text-muted">
        <Link to="/privacidade" className="hover:underline">
          Política de Privacidade
        </Link>
        {" · "}
        <Link to="/termos" className="hover:underline">
          Termos de Uso
        </Link>
      </footer>
    </div>
  );
}
