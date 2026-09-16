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

const ROTULOS_CANAL: Record<string, string> = { email: "E-mail", whatsapp: "WhatsApp", linkedin: "LinkedIn" };

function paraPercentual(valor: number | null | undefined): string {
  if (valor === null || valor === undefined) return "—";
  return `${(valor * 100).toFixed(1)}%`;
}

export function RelatorioEntrega() {
  const [relatorio, setRelatorio] = useState<RelatorioEntrega | null>(null);
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

  useEffect(() => {
    carregar();
  }, []);

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

  async function suprimirContato(decisorId: number) {
    if (suprimindoDecisorId !== null) return;
    setSuprimindoDecisorId(decisorId);
    setErro(null);
    try {
      // A rota vive sob /contas/{conta_id}/..., mas `optout_service` só
      // precisa do decisor_id — qualquer conta_id no path funciona; usamos
      // a conta real só por clareza semântica da URL.
      const contato = relatorio?.contatos_com_bounce.find((item) => item.decisor_id === decisorId);
      await api.post(`/contas/${contato?.conta_id ?? 0}/decisores/${decisorId}/suprimir`);
      setMensagem("Contato excluído — não vai mais receber mensagens.");
      await carregar();
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível excluir o contato.");
    } finally {
      setSuprimindoDecisorId(null);
    }
  }

  const saude = relatorio?.saude_email;

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
        <SectionLabel>Contatos com e-mail rejeitado</SectionLabel>
        {relatorio && relatorio.contatos_com_bounce.length === 0 && (
          <div className="text-[12px] text-muted">Nenhum contato com bounce registrado.</div>
        )}
        <div className="flex flex-col gap-2">
          {relatorio?.contatos_com_bounce.map((contato) => (
            <div
              key={`${contato.decisor_id ?? "avulso"}-${contato.bounce_em}`}
              className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-border p-2.5 text-[12px]"
            >
              <div>
                <div className="font-semibold text-text">
                  {contato.nome} {contato.conta_nome && <span className="text-muted">· {contato.conta_nome}</span>}
                </div>
                <div className="text-muted">
                  {contato.email ?? "sem e-mail"} · {contato.motivo_bounce ?? "motivo não informado"} ·{" "}
                  {new Date(contato.bounce_em).toLocaleString("pt-BR")}
                </div>
              </div>
              <div className="flex flex-shrink-0 items-center gap-2">
                {contato.conta_id !== null && (
                  <Button size="sm" variant="ghost" onClick={() => setContaEmEdicaoId(contato.conta_id)}>
                    Editar e-mail
                  </Button>
                )}
                {contato.decisor_id !== null && (
                  <Button
                    size="sm"
                    variant="danger"
                    disabled={suprimindoDecisorId === contato.decisor_id}
                    onClick={() => suprimirContato(contato.decisor_id!)}
                  >
                    {suprimindoDecisorId === contato.decisor_id ? "Excluindo..." : "Excluir contato"}
                  </Button>
                )}
              </div>
            </div>
          ))}
        </div>
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
