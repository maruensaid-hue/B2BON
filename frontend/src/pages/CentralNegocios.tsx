import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { Card } from "@/components/ui/Card";
import { api } from "@/lib/api";

interface CotacaoMoeda {
  codigo: string;
  nome: string;
  valor: number;
  variacao_pct: number;
}

interface Ibovespa {
  pontos: number;
  variacao_pct: number;
}

interface Mercado {
  ibovespa: Ibovespa | null;
  cambio: CotacaoMoeda[];
}

interface Noticia {
  portal: string;
  titulo: string;
  link: string;
  publicado_em: string | null;
}

interface Dica {
  titulo: string;
  texto: string;
}

interface GrupoDicas {
  tema: string;
  dicas: Dica[];
}

const URL_B3 = "https://www.b3.com.br/pt_br/market-data-e-indices/";
const PORTAIS_NOTICIAS = ["UOL Economia", "G1 Economia", "InfoMoney"];

const FORMATADOR_PONTOS = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 0 });
const FORMATADOR_VALOR_MOEDA = new Intl.NumberFormat("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 4 });

function formatarVariacao(pct: number): string {
  return `${pct > 0 ? "+" : ""}${pct.toFixed(2)}%`;
}

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

function CartaoCotacao({ rotulo, valor, variacaoPct }: { rotulo: string; valor: string; variacaoPct: number }) {
  const positivo = variacaoPct > 0;
  const negativo = variacaoPct < 0;
  return (
    <div className="flex flex-col gap-1 rounded-lg border border-border bg-surf2 p-3.5">
      <div className="text-[10px] font-semibold tracking-wide text-muted uppercase">{rotulo}</div>
      <div className="text-[16px] font-bold text-text">{valor}</div>
      <div className={`text-[11.5px] font-semibold ${positivo ? "text-green" : negativo ? "text-red" : "text-muted"}`}>
        {formatarVariacao(variacaoPct)}
      </div>
    </div>
  );
}

function CartaoIndisponivel({ rotulo }: { rotulo: string }) {
  return (
    <div className="flex flex-col gap-1 rounded-lg border border-border bg-surf2 p-3.5">
      <div className="text-[10px] font-semibold tracking-wide text-muted uppercase">{rotulo}</div>
      <div className="text-[12px] text-muted">Indisponível no momento</div>
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
          <div className="text-[10px] font-semibold tracking-wider text-muted uppercase">Mercado</div>
          <a href={URL_B3} target="_blank" rel="noreferrer" className="text-[11px] text-cyan hover:underline">
            Ver na B3 ↗
          </a>
        </div>
        {carregando ? (
          <div className="text-[12px] text-muted">Carregando cotações...</div>
        ) : (
          <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-5">
            {mercado?.ibovespa ? (
              <CartaoCotacao
                rotulo="Ibovespa"
                valor={`${FORMATADOR_PONTOS.format(mercado.ibovespa.pontos)} pts`}
                variacaoPct={mercado.ibovespa.variacao_pct}
              />
            ) : (
              <CartaoIndisponivel rotulo="Ibovespa" />
            )}
            {mercado && mercado.cambio.length > 0
              ? mercado.cambio.map((moeda) => (
                  <CartaoCotacao
                    key={moeda.codigo}
                    rotulo={`${moeda.codigo} / BRL`}
                    valor={`R$ ${FORMATADOR_VALOR_MOEDA.format(moeda.valor)}`}
                    variacaoPct={moeda.variacao_pct}
                  />
                ))
              : !mercado?.ibovespa && <CartaoIndisponivel rotulo="Câmbio" />}
          </div>
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
