import { Link } from "react-router-dom";

import { Card } from "@/components/ui/Card";

interface LinkExterno {
  titulo: string;
  descricao: string;
  url: string;
}

interface Dica {
  titulo: string;
  texto: string;
}

interface GrupoDicas {
  tema: string;
  dicas: Dica[];
}

const LINK_B3: LinkExterno = {
  titulo: "B3 — Market Data e Índices",
  descricao: "Cotações, Ibovespa e indicadores oficiais da bolsa brasileira, direto na fonte.",
  url: "https://www.b3.com.br/pt_br/market-data-e-indices/",
};

const LINKS_NOTICIAS: LinkExterno[] = [
  {
    titulo: "UOL Economia",
    descricao: "As últimas notícias de economia e negócios do portal.",
    url: "https://economia.uol.com.br/",
  },
  {
    titulo: "G1 Economia",
    descricao: "Cobertura de mercado, dólar e indicadores em tempo real.",
    url: "https://g1.globo.com/economia/",
  },
  {
    titulo: "IstoÉ Dinheiro",
    descricao: "Reportagens e análises sobre empresas e mercado brasileiro.",
    url: "https://www.istoedinheiro.com.br/",
  },
];

// Conteúdo original, escrito pela B2B ON no tom da marca "O Vendedor
// Tubarão" (raio-X 2026-09-21) — não é trecho de nenhum livro real, só
// inspirado no espírito da marca (decisão confirmada com o usuário).
const GRUPOS_DICAS: GrupoDicas[] = [
  {
    tema: "Fechamento de negócios",
    dicas: [
      {
        titulo: "O silêncio depois da proposta",
        texto: "Depois de apresentar o preço, pare de falar. Quem fala primeiro depois de um número geralmente é quem cede primeiro.",
      },
      {
        titulo: "Feche em etapas, não de uma vez",
        texto: "Peça pequenos \"sins\" ao longo da conversa (data, orçamento, decisor) antes do fechamento final — cada sim pequeno reduz a resistência do sim grande.",
      },
    ],
  },
  {
    tema: "Vendas consultivas",
    dicas: [
      {
        titulo: "Venda o problema antes da solução",
        texto: "Antes de falar do produto, confirme em voz alta o problema que o cliente descreveu. Se ele concordar com o diagnóstico, a solução vira consequência lógica, não convencimento.",
      },
      {
        titulo: "Perguntas abrem, afirmações fecham",
        texto: "Nas primeiras conversas, pergunte mais do que afirme. Quem pergunta guia a conversa; quem afirma cedo demais, se define antes de entender o cliente.",
      },
    ],
  },
  {
    tema: "Quebra de resistência",
    dicas: [
      {
        titulo: "Nomeie a objeção antes do cliente",
        texto: "Se um problema é comum (\"está caro\", \"não é prioridade agora\"), traga você mesmo o assunto antes que o cliente precise levantar a guarda pra dizer.",
      },
      {
        titulo: "Objeção não é \"não\"",
        texto: "Trate objeção como pedido de mais informação, não como recusa. \"Está caro\" geralmente quer dizer \"ainda não vi valor suficiente pra esse preço\".",
      },
    ],
  },
  {
    tema: "PNL aplicada a vendas",
    dicas: [
      {
        titulo: "Espelhamento sutil",
        texto: "Ajustar o ritmo de fala e o tom pro nível do cliente (mais formal ou mais direto) cria rapport sem que ele perceba a técnica.",
      },
      {
        titulo: "Use os verbos do cliente",
        texto: "Se o cliente fala em termos visuais (\"eu vejo que...\"), responda visualmente (\"vou te mostrar\"); se fala em termos auditivos (\"isso soa bem\"), responda no mesmo canal. Reduz atrito na comunicação.",
      },
    ],
  },
  {
    tema: "Análise comportamental do cliente",
    dicas: [
      {
        titulo: "Decisor analítico pede dado, não discurso",
        texto: "Perfis mais técnicos/financeiros decidem por número e comparação — leve planilha, não só argumento.",
      },
      {
        titulo: "Decisor relacional decide por confiança",
        texto: "Perfis mais humanos/de time decidem por quem está do outro lado da mesa — invista tempo em relacionamento antes de forçar uma proposta.",
      },
    ],
  },
];

function CardLinkExterno({ titulo, descricao, url }: LinkExterno) {
  return (
    <a
      href={url}
      target="_blank"
      rel="noreferrer"
      className="flex flex-col gap-1 rounded-lg border border-border bg-surf2 p-3.5 transition-colors hover:border-cyan"
    >
      <div className="flex items-center justify-between gap-2">
        <div className="text-[13px] font-semibold text-text">{titulo}</div>
        <div className="text-[11px] text-cyan">↗</div>
      </div>
      <div className="text-[11.5px] text-muted">{descricao}</div>
    </a>
  );
}

/** Central de Negócios (raio-X 2026-09-21) — página pública, alcançável
 * pelo botão "Sair" da página de boas-vindas. 100% conteúdo estático no
 * frontend: B3/notícias são links de saída pros sites reais (nunca
 * cotação/manchete inventada aqui); dicas de venda são conteúdo
 * original da B2B ON. */
export function CentralNegocios() {
  return (
    <div className="mx-auto max-w-4xl p-5.5">
      <Link to="/" className="mb-4 inline-block text-[12px] text-cyan hover:underline">
        ← Voltar para o login
      </Link>

      <div className="mb-6">
        <div className="font-head text-2xl font-bold text-text">Central de Negócios</div>
        <div className="mt-1 text-[12.5px] text-muted">
          Mercado, notícias e dicas de vendas — curadoria da B2B ON pra quem vive de prospecção e fechamento.
        </div>
      </div>

      <Card className="mb-4">
        <div className="mb-3 text-[10px] font-semibold tracking-wider text-muted uppercase">Mercado</div>
        <CardLinkExterno {...LINK_B3} />
      </Card>

      <Card className="mb-4">
        <div className="mb-3 text-[10px] font-semibold tracking-wider text-muted uppercase">Notícias de negócios</div>
        <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-3">
          {LINKS_NOTICIAS.map((link) => (
            <CardLinkExterno key={link.url} {...link} />
          ))}
        </div>
      </Card>

      <Card>
        <div className="mb-1 text-[10px] font-semibold tracking-wider text-muted uppercase">
          Dicas — O Vendedor Tubarão
        </div>
        <div className="mb-3.5 text-[11px] text-muted">
          Conteúdo original da B2B ON, no espírito da marca — não são trechos literais de nenhum livro.
        </div>
        <div className="flex flex-col gap-5">
          {GRUPOS_DICAS.map((grupo) => (
            <div key={grupo.tema}>
              <div className="mb-2 text-[12px] font-bold text-cyan">{grupo.tema}</div>
              <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-2">
                {grupo.dicas.map((dica) => (
                  <div key={dica.titulo} className="rounded-lg bg-surf2 p-3">
                    <div className="mb-1 text-[12px] font-semibold text-text">{dica.titulo}</div>
                    <div className="text-[11.5px] leading-relaxed text-muted">{dica.texto}</div>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}
