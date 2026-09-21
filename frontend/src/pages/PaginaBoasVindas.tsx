import { Link } from "react-router-dom";

interface Diferencial {
  icone: string;
  titulo: string;
  texto: string;
}

const DIFERENCIAIS: Diferencial[] = [
  {
    icone: "🎯",
    titulo: "Prospecção de verdade, não só um CRM bonito",
    texto:
      "A maioria dos CRMs espera você trazer o lead. O Predator sai atrás: gera a lista a partir da base real da Receita Federal, enriquece com IA e escreve a cadência sozinho — você só entra quando tem gente pronta pra falar.",
  },
  {
    icone: "✅",
    titulo: "Zero mensagem sai sem você ver",
    texto:
      "A IA escreve, um humano aprova. Nenhuma cadência de e-mail, WhatsApp ou LinkedIn dispara sem passar pela sua revisão — diferente de robô de disparo automático que só reza pra não incomodar o cliente errado.",
  },
  {
    icone: "🐟",
    titulo: "Uma rede social só de empresas pagantes",
    texto:
      "O Shoal conecta sua empresa com outras assinantes da plataforma — parceria, indicação, fornecedor, tudo dentro do mesmo lugar onde você já trabalha, sem precisar sair pro LinkedIn.",
  },
  {
    icone: "🧠",
    titulo: "Aprende com os próprios erros",
    texto:
      "Toda vez que você edita uma mensagem da IA, essa correção vira regra — a próxima cadência já nasce melhor. Nenhum CRM tradicional faz isso sozinho.",
  },
  {
    icone: "◈",
    titulo: "CRM e prospecção na mesma tela",
    texto:
      "Não é um CRM de um lado e uma ferramenta de prospecção do outro, que você precisa integrar na mão. É uma coisa só, do primeiro contato até o negócio fechado.",
  },
  {
    icone: "🧭",
    titulo: "Sinais de oportunidade cruzando a rede",
    texto:
      "Fit de ICP contra a rede inteira do Shoal, necessidades declaradas por outras empresas, tudo virando sinal de negócio — sempre com o motivo explicado, nunca um número solto.",
  },
];

/** Página de boas-vindas pública (raio-X 2026-09-21) — raiz `/` pra
 * visitante deslogado, ANTES da tela de login. Comercial de propósito:
 * vende a plataforma com diferenciais reais já construídos (não é uma
 * lista genérica de features), não só descreve o produto neutro. */
export function PaginaBoasVindas() {
  return (
    <div className="min-h-screen bg-bg">
      <header className="border-b border-nav-border bg-nav-bg">
        <div className="mx-auto flex max-w-5xl items-center justify-between px-5.5 py-4">
          <div className="flex items-center gap-2.5">
            <div className="flex h-8.5 w-8.5 flex-shrink-0 items-center justify-center rounded-lg bg-gradient-to-br from-cyan to-[#005F7A] font-head text-[17px] font-black text-white">
              B
            </div>
            <div className="font-head text-[15px] font-extrabold text-nav-text">
              B2B <span className="text-cyan">ON</span>
            </div>
          </div>
          <Link to="/login" className="text-[12.5px] font-semibold text-nav-muted hover:text-nav-text">
            Fazer login
          </Link>
        </div>

        <div className="mx-auto max-w-3xl px-5.5 pt-8 pb-16 text-center">
          <h1 className="font-head text-[28px] leading-tight font-black text-nav-text sm:text-[36px]">
            O CRM que prospecta sozinho — e avisa quando é hora de fechar.
          </h1>
          <p className="mt-4 text-[14px] leading-relaxed text-nav-muted">
            B2B ON junta CRM, prospecção automatizada com IA e uma rede social só entre empresas
            assinantes numa ferramenta só. Sem módulo separado, sem sistema paralelo, sem plugin
            de terceiro pra fazer as partes conversarem.
          </p>
          <div className="mt-7 flex flex-col items-center justify-center gap-3 sm:flex-row">
            <Link
              to="/criar-conta"
              className="w-full rounded-lg bg-cyan px-6 py-3 text-center text-[13.5px] font-bold text-white transition-transform hover:scale-[1.02] sm:w-auto"
            >
              Comece a usar gratuitamente
            </Link>
            <Link
              to="/login"
              className="w-full rounded-lg border border-nav-border px-6 py-3 text-center text-[13.5px] font-bold text-nav-text transition-colors hover:bg-nav-hover sm:w-auto"
            >
              Fazer login
            </Link>
          </div>
          <div className="mt-3 text-[11px] text-nav-muted">Sem custo pra criar sua conta — você escolhe o plano na hora.</div>
        </div>
      </header>

      <main className="mx-auto max-w-5xl px-5.5 py-12">
        <div className="mb-8 text-center">
          <div className="text-[10px] font-semibold tracking-widest text-cyan uppercase">
            O que diferencia a B2B ON
          </div>
          <div className="mt-1.5 font-head text-xl font-bold text-text">
            Não é mais um CRM. É o que falta na maioria das soluções tradicionais.
          </div>
        </div>

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {DIFERENCIAIS.map((item) => (
            <div key={item.titulo} className="rounded-xl border border-border bg-surf p-4.5">
              <div className="text-xl">{item.icone}</div>
              <div className="mt-2 text-[13px] font-bold text-text">{item.titulo}</div>
              <div className="mt-1.5 text-[12px] leading-relaxed text-muted">{item.texto}</div>
            </div>
          ))}
        </div>

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

        <div className="mt-10 text-center">
          <Link to="/central-de-negocios" className="text-[12px] text-muted hover:text-cyan hover:underline">
            Sair — ver notícias de negócios e dicas de vendas
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
