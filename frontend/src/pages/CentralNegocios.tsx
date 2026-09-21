import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { Card } from "@/components/ui/Card";
import { api } from "@/lib/api";

interface CotacaoMoeda {
  codigo: string;
  nome: string;
  valor: number;
  variacao_pct: number;
}

interface PontoSerie {
  data: string;
  valor: number;
}

interface Indice {
  nome: string;
  pontos: number;
  variacao_pct: number;
  serie: PontoSerie[];
}

interface Mercado {
  indices: Indice[];
  cambio: CotacaoMoeda[];
}

interface Noticia {
  portal: string;
  titulo: string;
  link: string;
  publicado_em: string | null;
}

interface Dica {
  emoji: string;
  titulo: string;
  texto: string;
}

interface GrupoDicas {
  tema: string;
  emoji: string;
  imagem: string;
  dicas: Dica[];
}

const URL_B3 = "https://www.b3.com.br/pt_br/market-data-e-indices/";
// Fotos reais do Unsplash (licença Unsplash — uso livre, sem precisar de
// permissão/atribuição), pedidas pelo usuário pra ilustrar os cards de
// dicas. IDs conferidos visualmente antes de escolher (raio-X 2026-09-21).
const IMG_HERO_DICAS = "https://images.unsplash.com/photo-1600880292203-757bb62b4baf?w=900&q=70&auto=format&fit=crop";
const PORTAIS_NOTICIAS = ["UOL Economia", "G1 Economia", "InfoMoney"];
const INTERVALO_CARROSSEL_MS = 6000;

const FORMATADOR_PONTOS = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 0 });
// Ativos de alto valor (Bitcoin, Ouro) ficam ilegíveis com 4 casas decimais
// e câmbio comum (USD/EUR) perde precisão com só 2 — cada faixa de valor
// usa a formatação que faz sentido pra ela.
const FORMATADOR_VALOR_ALTO = new Intl.NumberFormat("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const FORMATADOR_VALOR_BAIXO = new Intl.NumberFormat("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 4 });

function formatarValorMoeda(valor: number): string {
  return valor >= 100 ? FORMATADOR_VALOR_ALTO.format(valor) : FORMATADOR_VALOR_BAIXO.format(valor);
}

function formatarVariacao(pct: number): string {
  return `${pct > 0 ? "+" : ""}${pct.toFixed(2)}%`;
}

// Conteúdo original, escrito pela B2B ON no tom da marca "O Vendedor
// Tubarão" (raio-X 2026-09-21) — não é trecho de nenhum livro real, só
// inspirado no espírito da marca (decisão confirmada com o usuário).
const GRUPOS_DICAS: GrupoDicas[] = [
  {
    tema: "Fechamento de negócios",
    emoji: "🤝",
    imagem: "https://images.unsplash.com/photo-1521791136064-7986c2920216?w=500&q=65&auto=format&fit=crop",
    dicas: [
      {
        emoji: "🤫",
        titulo: "O silêncio depois da proposta",
        texto: "Depois de apresentar o preço, pare de falar. Quem fala primeiro depois de um número geralmente é quem cede primeiro.",
      },
      {
        emoji: "🪜",
        titulo: "Feche em etapas, não de uma vez",
        texto: "Peça pequenos \"sins\" ao longo da conversa (data, orçamento, decisor) antes do fechamento final — cada sim pequeno reduz a resistência do sim grande.",
      },
    ],
  },
  {
    tema: "Vendas consultivas",
    emoji: "🧭",
    imagem: "https://images.unsplash.com/photo-1552664730-d307ca884978?w=500&q=65&auto=format&fit=crop",
    dicas: [
      {
        emoji: "🩺",
        titulo: "Venda o problema antes da solução",
        texto: "Antes de falar do produto, confirme em voz alta o problema que o cliente descreveu. Se ele concordar com o diagnóstico, a solução vira consequência lógica, não convencimento.",
      },
      {
        emoji: "❓",
        titulo: "Perguntas abrem, afirmações fecham",
        texto: "Nas primeiras conversas, pergunte mais do que afirme. Quem pergunta guia a conversa; quem afirma cedo demais, se define antes de entender o cliente.",
      },
    ],
  },
  {
    tema: "Quebra de resistência",
    emoji: "🛡️",
    imagem: "https://images.unsplash.com/photo-1507679799987-c73779587ccf?w=500&q=65&auto=format&fit=crop",
    dicas: [
      {
        emoji: "🎯",
        titulo: "Nomeie a objeção antes do cliente",
        texto: "Se um problema é comum (\"está caro\", \"não é prioridade agora\"), traga você mesmo o assunto antes que o cliente precise levantar a guarda pra dizer.",
      },
      {
        emoji: "🔄",
        titulo: "Objeção não é \"não\"",
        texto: "Trate objeção como pedido de mais informação, não como recusa. \"Está caro\" geralmente quer dizer \"ainda não vi valor suficiente pra esse preço\".",
      },
    ],
  },
  {
    tema: "PNL aplicada a vendas",
    emoji: "🧠",
    imagem: "https://images.unsplash.com/photo-1454165804606-c3d57bc86b40?w=500&q=65&auto=format&fit=crop",
    dicas: [
      {
        emoji: "🪞",
        titulo: "Espelhamento sutil",
        texto: "Ajustar o ritmo de fala e o tom pro nível do cliente (mais formal ou mais direto) cria rapport sem que ele perceba a técnica.",
      },
      {
        emoji: "💬",
        titulo: "Use os verbos do cliente",
        texto: "Se o cliente fala em termos visuais (\"eu vejo que...\"), responda visualmente (\"vou te mostrar\"); se fala em termos auditivos (\"isso soa bem\"), responda no mesmo canal. Reduz atrito na comunicação.",
      },
    ],
  },
  {
    tema: "Análise comportamental do cliente",
    emoji: "👥",
    imagem: "https://images.unsplash.com/photo-1573497019940-1c28c88b4f3e?w=500&q=65&auto=format&fit=crop",
    dicas: [
      {
        emoji: "📊",
        titulo: "Decisor analítico pede dado, não discurso",
        texto: "Perfis mais técnicos/financeiros decidem por número e comparação — leve planilha, não só argumento.",
      },
      {
        emoji: "❤️",
        titulo: "Decisor relacional decide por confiança",
        texto: "Perfis mais humanos/de time decidem por quem está do outro lado da mesa — invista tempo em relacionamento antes de forçar uma proposta.",
      },
    ],
  },
];

function Variacao({ pct }: { pct: number }) {
  const positivo = pct > 0;
  const negativo = pct < 0;
  return (
    <span className={`font-semibold ${positivo ? "text-green" : negativo ? "text-red" : "text-muted"}`}>
      {formatarVariacao(pct)}
    </span>
  );
}

/** Carrossel dos índices de bolsa (Ibovespa/Dow Jones/Nasdaq) — troca
 * sozinho a cada `INTERVALO_CARROSSEL_MS`, com bolinhas clicáveis pra
 * navegar manualmente. Gráfico de linha com a série do último mês. */
function CarrosselIndices({ indices }: { indices: Indice[] }) {
  const [ativo, setAtivo] = useState(0);

  useEffect(() => {
    if (indices.length < 2) return;
    const intervalo = setInterval(() => setAtivo((atual) => (atual + 1) % indices.length), INTERVALO_CARROSSEL_MS);
    return () => clearInterval(intervalo);
  }, [indices.length]);

  if (indices.length === 0) {
    return <div className="text-[12px] text-muted">Índices indisponíveis no momento.</div>;
  }

  const indice = indices[Math.min(ativo, indices.length - 1)];

  return (
    <div>
      <div className="mb-2 flex items-end justify-between gap-2">
        <div>
          <div className="text-[13px] font-bold text-text">{indice.nome}</div>
          <div className="text-[11.5px] text-muted">
            {FORMATADOR_PONTOS.format(indice.pontos)} pts · <Variacao pct={indice.variacao_pct} />
          </div>
        </div>
        {indices.length > 1 && (
          <div className="flex gap-1.5">
            {indices.map((item, posicao) => (
              <button
                key={item.nome}
                type="button"
                onClick={() => setAtivo(posicao)}
                aria-label={`Ver ${item.nome}`}
                className={`h-1.5 w-5 rounded-full transition-colors ${posicao === ativo ? "bg-cyan" : "bg-border hover:bg-muted"}`}
              />
            ))}
          </div>
        )}
      </div>
      <div style={{ height: 160 }}>
        {indice.serie.length > 1 ? (
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={indice.serie}>
              <XAxis dataKey="data" tick={{ fill: "var(--color-muted)", fontSize: 9 }} interval="preserveStartEnd" />
              <YAxis
                domain={["auto", "auto"]}
                tick={{ fill: "var(--color-muted)", fontSize: 9 }}
                width={54}
                tickFormatter={(valor: number) => FORMATADOR_PONTOS.format(valor)}
              />
              <Tooltip
                contentStyle={{ background: "var(--color-surf2)", border: "1px solid var(--color-border)" }}
                labelStyle={{ color: "var(--color-text)" }}
                formatter={(valor) => FORMATADOR_PONTOS.format(Number(valor))}
              />
              <Line
                type="monotone"
                dataKey="valor"
                stroke="var(--color-cyan)"
                strokeWidth={2}
                dot={false}
                isAnimationActive={false}
              />
            </LineChart>
          </ResponsiveContainer>
        ) : (
          <div className="flex h-full items-center justify-center text-[11.5px] text-muted">
            Série histórica indisponível no momento.
          </div>
        )}
      </div>
    </div>
  );
}

/** Janela de câmbio/cripto/ouro, lado a lado numa linha só (formato
 * pedido pelo usuário: "USD = R$ 5,00 | EUR = R$ 6,00 | Bitcoin = R$
 * 134.000,00"). */
function JanelaCotacoes({ cambio }: { cambio: CotacaoMoeda[] }) {
  if (cambio.length === 0) {
    return <div className="text-[12px] text-muted">Cotações indisponíveis no momento.</div>;
  }
  return (
    <div className="flex flex-wrap items-center gap-x-2 gap-y-1.5 text-[12.5px]">
      {cambio.map((item, posicao) => (
        <span key={item.codigo} className="flex items-center gap-2">
          <span>
            <span className="font-semibold text-text">{item.nome}</span>{" "}
            <span className="text-muted">= R$ {formatarValorMoeda(item.valor)}</span>{" "}
            <Variacao pct={item.variacao_pct} />
          </span>
          {posicao < cambio.length - 1 && <span className="text-border">|</span>}
        </span>
      ))}
    </div>
  );
}

/** Central de Negócios (raio-X 2026-09-21, dados ao vivo 2026-09-21) —
 * página pública, alcançável pelo botão "Sair" da página de boas-vindas.
 * B3/câmbio vêm de `GET /central-negocios/mercado` (Yahoo Finance +
 * AwesomeAPI, cacheado 15min no backend); notícias vêm de
 * `GET /central-negocios/noticias` (RSS real de cada portal) — nunca
 * cotação/manchete inventada aqui. Dicas de venda continuam conteúdo
 * original estático da B2B ON. */
export function CentralNegocios() {
  const [mercado, setMercado] = useState<Mercado | null>(null);
  const [noticias, setNoticias] = useState<Noticia[] | null>(null);
  const [carregando, setCarregando] = useState(true);

  useEffect(() => {
    Promise.allSettled([api.get<Mercado>("/central-negocios/mercado"), api.get<Noticia[]>("/central-negocios/noticias")]).then(
      ([resultadoMercado, resultadoNoticias]) => {
        if (resultadoMercado.status === "fulfilled") setMercado(resultadoMercado.value);
        if (resultadoNoticias.status === "fulfilled") setNoticias(resultadoNoticias.value);
        setCarregando(false);
      },
    );
  }, []);

  return (
    <div className="mx-auto max-w-4xl p-5.5">
      <Link to="/" className="mb-4 inline-block text-[12px] text-cyan hover:underline">
        ← Voltar para a tela de boas-vindas
      </Link>

      <div className="mb-6">
        <div className="font-head text-2xl font-bold text-text">Central de Negócios</div>
        <div className="mt-1 text-[12.5px] text-muted">
          Mercado, notícias e dicas de vendas — curadoria da B2B ON pra quem vive de prospecção e fechamento.
        </div>
      </div>

      <Card className="mb-4">
        <div className="mb-3 flex items-center justify-between gap-2">
          <div className="text-[10px] font-semibold tracking-wider text-muted uppercase">Índices — B3, Nova Iorque e Nasdaq</div>
          <a href={URL_B3} target="_blank" rel="noreferrer" className="text-[11px] text-cyan hover:underline">
            Ver na B3 ↗
          </a>
        </div>
        {carregando ? (
          <div className="text-[12px] text-muted">Carregando índices...</div>
        ) : (
          <CarrosselIndices indices={mercado?.indices ?? []} />
        )}
      </Card>

      <Card className="mb-4">
        <div className="mb-3 text-[10px] font-semibold tracking-wider text-muted uppercase">Câmbio, cripto e ouro</div>
        {carregando ? (
          <div className="text-[12px] text-muted">Carregando cotações...</div>
        ) : (
          <JanelaCotacoes cambio={mercado?.cambio ?? []} />
        )}
      </Card>

      <Card className="mb-4">
        <div className="mb-3 text-[10px] font-semibold tracking-wider text-muted uppercase">Notícias de negócios</div>
        {carregando ? (
          <div className="text-[12px] text-muted">Carregando notícias...</div>
        ) : (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            {PORTAIS_NOTICIAS.map((portal) => {
              const materias = (noticias ?? []).filter((noticia) => noticia.portal === portal);
              return (
                <div key={portal}>
                  <div className="mb-2 text-[11.5px] font-bold text-cyan">{portal}</div>
                  {materias.length === 0 ? (
                    <div className="text-[11.5px] text-muted">Sem matérias disponíveis no momento.</div>
                  ) : (
                    <ul className="flex flex-col gap-2">
                      {materias.map((materia) => (
                        <li key={materia.link}>
                          <a
                            href={materia.link}
                            target="_blank"
                            rel="noreferrer"
                            className="text-[11.5px] leading-snug text-text hover:text-cyan hover:underline"
                          >
                            {materia.titulo}
                          </a>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </Card>

      <Card>
        <div className="relative mb-4 overflow-hidden rounded-xl">
          <img
            src={IMG_HERO_DICAS}
            alt="Time comemorando um negócio fechado"
            loading="lazy"
            className="h-32 w-full object-cover sm:h-40"
          />
          <div className="absolute inset-0 flex flex-col justify-end bg-gradient-to-t from-black/75 via-black/20 to-transparent p-3.5">
            <div className="text-[15px] font-bold text-white">🦈 Dicas — O Vendedor Tubarão</div>
          </div>
        </div>
        <div className="flex flex-col gap-4">
          {GRUPOS_DICAS.map((grupo, indice) => (
            <div
              key={grupo.tema}
              className="animate-fade-in-up overflow-hidden rounded-xl border border-border bg-surf2 transition-shadow duration-200 hover:shadow-lg"
              style={{ animationDelay: `${indice * 80}ms` }}
            >
              <div className="relative">
                <img src={grupo.imagem} alt={grupo.tema} loading="lazy" className="h-20 w-full object-cover" />
                <div className="absolute inset-0 bg-gradient-to-r from-black/70 via-black/30 to-transparent" />
                <div className="absolute inset-0 flex items-center gap-2 px-3.5">
                  <span className="text-[22px] drop-shadow">{grupo.emoji}</span>
                  <span className="text-[13px] font-bold text-white drop-shadow">{grupo.tema}</span>
                </div>
              </div>
              <div className="grid grid-cols-1 gap-2.5 p-3.5 sm:grid-cols-2">
                {grupo.dicas.map((dica) => (
                  <div
                    key={dica.titulo}
                    className="rounded-lg border border-border bg-surf p-3 transition-all duration-200 hover:-translate-y-0.5 hover:border-cyan/50"
                  >
                    <div className="mb-1 flex items-start gap-1.5 text-[12px] font-semibold text-text">
                      <span className="text-[14px] leading-none">{dica.emoji}</span>
                      <span>{dica.titulo}</span>
                    </div>
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
