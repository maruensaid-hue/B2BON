import { useEffect, useState } from "react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, SectionLabel } from "@/components/ui/Card";
import { KpiCard } from "@/components/ui/KpiCard";
import { ContaDetalheModal } from "@/pages/prospeccao/ContaDetalheModal";
import { api, ApiError } from "@/lib/api";

interface SaudeCanalEmail {
  canal: string;
  enviados: number;
  bounces: number;
  spam_reports: number;
  taxa_bounce: number;
  taxa_spam: number;
  pausado: boolean;
  limiar_bounce: number;
  limiar_spam: number;
}

interface ContatoComBounce {
  decisor_id: number | null;
  conta_id: number | null;
  nome: string;
  email: string | null;
  conta_nome: string | null;
  canal: string;
  motivo_bounce: string | null;
  bounce_em: string;
}

interface RelatorioEntrega {
  saude_email: SaudeCanalEmail;
  taxa_abertura_email: number | null;
  taxa_resposta_por_canal: Record<string, number>;
  contatos_com_bounce: ContatoComBounce[];
}

interface EnvioEmail {
  origem: "cadencia" | "campanha";
  origem_nome: string;
  decisor_id: number | null;
  conta_id: number | null;
  nome: string;
  email: string | null;
  conta_nome: string | null;
  status: "erro" | "enviado" | "aberto" | "pendente" | "cancelado";
  detalhe: string | null;
  enviado_em: string | null;
  criado_em: string;
}

interface ListaEnviosEmail {
  itens: EnvioEmail[];
  total: number;
  contagem_por_status: Record<string, number>;
}

const ROTULOS_CANAL: Record<string, string> = { email: "E-mail", whatsapp: "WhatsApp", linkedin: "LinkedIn" };

const ABAS_STATUS: { valor: string; rotulo: string }[] = [
  { valor: "todos", rotulo: "Todos" },
  { valor: "erro", rotulo: "Erro" },
  { valor: "enviado", rotulo: "Enviado" },
  { valor: "aberto", rotulo: "Aberto" },
  { valor: "pendente", rotulo: "Pendente" },
  { valor: "cancelado", rotulo: "Cancelado" },
];

const TOM_STATUS: Record<string, "red" | "green" | "violet" | "amber" | "muted"> = {
  erro: "red",
  enviado: "green",
  aberto: "violet",
  pendente: "amber",
  cancelado: "muted",
};

const ROTULO_STATUS: Record<string, string> = {
  erro: "Erro",
  enviado: "Enviado",
  aberto: "Aberto",
  pendente: "Pendente",
  cancelado: "Cancelado",
};

const LIMITE_POR_PAGINA = 50;

function paraPercentual(valor: number | null | undefined): string {
  if (valor === null || valor === undefined) return "—";
  return `${(valor * 100).toFixed(1)}%`;
}

export function RelatorioEntrega() {
  const [relatorio, setRelatorio] = useState<RelatorioEntrega | null>(null);
  const [envios, setEnvios] = useState<ListaEnviosEmail | null>(null);
  const [filtroStatus, setFiltroStatus] = useState("todos");
  const [pagina, setPagina] = useState(0);
  const [carregandoEnvios, setCarregandoEnvios] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [mensagem, setMensagem] = useState<string | null>(null);
  const [reativando, setReativando] = useState(false);
  const [suprimindoDecisorId, setSuprimindoDecisorId] = useState<number | null>(null);
  const [contaEmEdicaoId, setContaEmEdicaoId] = useState<number | null>(null);

  async function carregar() {
    try {
      setRelatorio(await api.get<RelatorioEntrega>("/relatorio-entrega"));
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível carregar o relatório.");
    }
  }

  async function carregarEnvios(status: string, offset: number) {
    setCarregandoEnvios(true);
    try {
      const params = new URLSearchParams({
        status,
        limite: String(LIMITE_POR_PAGINA),
        offset: String(offset * LIMITE_POR_PAGINA),
      });
      setEnvios(await api.get<ListaEnviosEmail>(`/relatorio-entrega/envios?${params.toString()}`));
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível carregar o detalhamento de envios.");
    } finally {
      setCarregandoEnvios(false);
    }
  }

  useEffect(() => {
    carregar();
  }, []);

  useEffect(() => {
    carregarEnvios(filtroStatus, pagina);
  }, [filtroStatus, pagina]);

  async function reativarCanalEmail() {
    if (reativando) return;
    setReativando(true);
    setErro(null);
    try {
      await api.post("/canais/email/reativar");
      setMensagem("Canal de e-mail reativado.");
      await carregar();
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível reativar o canal.");
    } finally {
      setReativando(false);
    }
  }

  async function suprimirContato(decisorId: number, contaId: number | null) {
    if (suprimindoDecisorId !== null) return;
    setSuprimindoDecisorId(decisorId);
    setErro(null);
    try {
      // A rota vive sob /contas/{conta_id}/..., mas `optout_service` só
      // precisa do decisor_id — qualquer conta_id no path funciona; usamos
      // a conta real só por clareza semântica da URL.
      await api.post(`/contas/${contaId ?? 0}/decisores/${decisorId}/suprimir`);
      setMensagem("Contato excluído — não vai mais receber mensagens.");
      await carregar();
      await carregarEnvios(filtroStatus, pagina);
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível excluir o contato.");
    } finally {
      setSuprimindoDecisorId(null);
    }
  }

  const saude = relatorio?.saude_email;
  const totalPaginas = envios ? Math.max(1, Math.ceil(envios.total / LIMITE_POR_PAGINA)) : 1;

  return (
    <div className="p-5.5">
      <div className="mb-5">
        <div className="font-head text-xl font-bold">Relatório de Entrega</div>
        <div className="mt-0.5 text-[11px] text-muted">
          Entregabilidade de e-mail e taxa de resposta por canal — o que a plataforma consegue medir de verdade
        </div>
      </div>

      {erro && <div className="mb-4 text-[12px] text-red">{erro}</div>}
      {mensagem && <div className="mb-4 text-[12px] text-green">{mensagem}</div>}

      <Card className="mb-4">
        <div className="mb-3 flex items-center justify-between">
          <SectionLabel>E-mail — últimos 7 dias</SectionLabel>
          <Badge tone={saude?.pausado ? "red" : "green"}>{saude?.pausado ? "Pausado" : "Saudável"}</Badge>
        </div>
        <div className="mb-3 grid grid-cols-2 gap-2.5 sm:grid-cols-4">
          <KpiCard label="Enviados" value={saude?.enviados ?? "—"} />
          <KpiCard
            label="Taxa de bounce"
            value={saude ? paraPercentual(saude.taxa_bounce) : "—"}
            sub={saude ? `limite: ${paraPercentual(saude.limiar_bounce)}` : undefined}
            colorClassName={saude?.pausado ? "text-red" : "text-cyan"}
          />
          <KpiCard
            label="Taxa de spam"
            value={saude ? paraPercentual(saude.taxa_spam) : "—"}
            sub={saude ? `limite: ${paraPercentual(saude.limiar_spam)}` : undefined}
          />
          <KpiCard label="Taxa de abertura" value={paraPercentual(relatorio?.taxa_abertura_email)} colorClassName="text-violet" />
        </div>
        {saude?.pausado && (
          <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg bg-red/10 p-3 text-[12px] text-text">
            <span>
              Canal de e-mail pausado automaticamente — taxa de bounce/spam acima do limite. Corrija ou exclua os
              contatos problemáticos abaixo antes de reativar.
            </span>
            <Button size="sm" variant="danger" disabled={reativando} onClick={reativarCanalEmail}>
              {reativando ? "Reativando..." : "Reativar canal"}
            </Button>
          </div>
        )}
      </Card>

      <Card className="mb-4">
        <SectionLabel>Taxa de resposta por canal</SectionLabel>
        <div className="flex flex-wrap gap-2.5">
          {Object.entries(relatorio?.taxa_resposta_por_canal ?? {}).map(([canal, taxa]) => (
            <KpiCard key={canal} label={ROTULOS_CANAL[canal] ?? canal} value={paraPercentual(taxa)} />
          ))}
          {relatorio && Object.keys(relatorio.taxa_resposta_por_canal).length === 0 && (
            <div className="text-[12px] text-muted">Nenhuma mensagem enviada ainda nesse período.</div>
          )}
        </div>
        <div className="mt-3 text-[11px] text-muted">
          WhatsApp e LinkedIn não têm confirmação de entrega/leitura rastreada — só a taxa de resposta acima é
          medida pra esses dois canais. A proteção contra bounce/pausa automática só existe para e-mail, e só
          para quem usa o e-mail compartilhado da B2B ON (contas com SMTP próprio não passam por esse rastreio).
        </div>
      </Card>

      <Card>
        <div className="mb-3 flex items-center justify-between">
          <SectionLabel>Detalhamento de envios de e-mail — por destinatário</SectionLabel>
          <span className="text-[11px] text-muted">{envios?.total ?? 0} destinatário(s) no filtro atual</span>
        </div>
        <div className="mb-3 flex flex-wrap gap-1.5">
          {ABAS_STATUS.map((aba) => {
            // `envios.total` reflete só o filtro selecionado no momento —
            // pra rotular a aba "Todos" com o total geral, soma-se
            // `contagem_por_status`, que o backend sempre calcula sem filtro.
            const totalGeral = envios
              ? Object.values(envios.contagem_por_status).reduce((soma, valor) => soma + valor, 0)
              : undefined;
            const contagem = envios?.contagem_por_status[aba.valor];
            const totalAba = aba.valor === "todos" ? totalGeral : contagem;
            return (
              <Button
                key={aba.valor}
                size="sm"
                variant={filtroStatus === aba.valor ? "primary" : "ghost"}
                onClick={() => {
                  setFiltroStatus(aba.valor);
                  setPagina(0);
                }}
              >
                {aba.rotulo} {totalAba !== undefined && `(${totalAba})`}
              </Button>
            );
          })}
        </div>

        {carregandoEnvios && <div className="text-[12px] text-muted">Carregando...</div>}
        {!carregandoEnvios && envios && envios.itens.length === 0 && (
          <div className="text-[12px] text-muted">Nenhum envio de e-mail nesse filtro.</div>
        )}

        <div className="flex flex-col gap-2">
          {!carregandoEnvios &&
            envios?.itens.map((item, indice) => (
              <div
                key={`${item.decisor_id ?? "avulso"}-${item.origem}-${item.criado_em}-${indice}`}
                className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-border p-2.5 text-[12px]"
              >
                <div>
                  <div className="flex items-center gap-2">
                    <Badge tone={TOM_STATUS[item.status]}>{ROTULO_STATUS[item.status]}</Badge>
                    <span className="font-semibold text-text">
                      {item.nome} {item.conta_nome && <span className="text-muted">· {item.conta_nome}</span>}
                    </span>
                  </div>
                  <div className="text-muted">
                    {item.email ?? "sem e-mail"} · {item.origem_nome}
                    {item.detalhe && <> · {item.detalhe}</>} ·{" "}
                    {new Date(item.enviado_em ?? item.criado_em).toLocaleString("pt-BR")}
                  </div>
                </div>
                {item.status === "erro" && (
                  <div className="flex flex-shrink-0 items-center gap-2">
                    {item.conta_id !== null && (
                      <Button size="sm" variant="ghost" onClick={() => setContaEmEdicaoId(item.conta_id)}>
                        Editar e-mail
                      </Button>
                    )}
                    {item.decisor_id !== null && (
                      <Button
                        size="sm"
                        variant="danger"
                        disabled={suprimindoDecisorId === item.decisor_id}
                        onClick={() => suprimirContato(item.decisor_id!, item.conta_id)}
                      >
                        {suprimindoDecisorId === item.decisor_id ? "Excluindo..." : "Excluir contato"}
                      </Button>
                    )}
                  </div>
                )}
              </div>
            ))}
        </div>

        {envios && envios.total > LIMITE_POR_PAGINA && (
          <div className="mt-3 flex items-center justify-between text-[11px] text-muted">
            <Button size="sm" variant="ghost" disabled={pagina === 0} onClick={() => setPagina((p) => Math.max(0, p - 1))}>
              ← Anterior
            </Button>
            <span>
              Página {pagina + 1} de {totalPaginas}
            </span>
            <Button
              size="sm"
              variant="ghost"
              disabled={pagina + 1 >= totalPaginas}
              onClick={() => setPagina((p) => p + 1)}
            >
              Próxima →
            </Button>
          </div>
        )}
      </Card>

      {contaEmEdicaoId !== null && (
        <ContaDetalheModal
          contaId={contaEmEdicaoId}
          onClose={() => setContaEmEdicaoId(null)}
          onAtualizado={carregar}
        />
      )}
    </div>
  );
}
