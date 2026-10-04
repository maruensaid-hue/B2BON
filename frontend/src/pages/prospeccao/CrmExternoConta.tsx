import { useCallback, useEffect, useState } from "react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { api, ApiError } from "@/lib/api";

interface Situacao {
  verificado: boolean;
  bloqueio: string | null;
  contatos: { decisor_id: number; bloqueio: string | null }[];
  enviada_para: string[];
  escrita_disponivel: boolean;
}

/** D-087: o que o CRM do cliente diz desta conta (deduplicação) e o botão
 * para enviá-la ao CRM. Some quando não há CRM conectado. */
export function CrmExternoConta({ contaId }: { contaId: number }) {
  const [situacao, setSituacao] = useState<Situacao | null>(null);
  const [mensagem, setMensagem] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);

  const carregar = useCallback(() => {
    api
      .get<Situacao>(`/contas/${contaId}/crm-externo`)
      .then(setSituacao)
      .catch(() => setSituacao(null));
  }, [contaId]);

  useEffect(carregar, [carregar]);

  if (!situacao || (!situacao.verificado && !situacao.escrita_disponivel)) return null;
  const contatosBloqueados = situacao.contatos.filter((c) => c.bloqueio).length;

  async function enviar() {
    setEnviando(true);
    try {
      const r = await api.post<{ enfileirados: number }>(`/contas/${contaId}/enviar-crm`);
      setMensagem(
        r.enfileirados > 0
          ? "Na fila: a empresa e os contatos vão para o CRM em alguns minutos (o que já existe lá não é alterado)."
          : "Esta conta já estava na fila ou já foi enviada.",
      );
      carregar();
    } catch (error) {
      setMensagem(error instanceof ApiError ? error.message : "Não foi possível enviar ao CRM.");
    } finally {
      setEnviando(false);
    }
  }

  return (
    <div className="mb-4 flex flex-col gap-1.5 rounded-md border border-border p-2 text-[11px]" data-testid="crm-externo-conta">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-semibold text-text">CRM do cliente</span>
        {situacao.bloqueio ? (
          <Badge tone="amber">{situacao.bloqueio}</Badge>
        ) : situacao.verificado ? (
          <Badge tone="green">Livre para abordar</Badge>
        ) : null}
        {contatosBloqueados > 0 && <Badge tone="red">{contatosBloqueados} contato(s) com opt-out no CRM</Badge>}
        {situacao.enviada_para.length > 0 && <Badge tone="cyan">Já no CRM: {situacao.enviada_para.join(", ")}</Badge>}
      </div>
      {situacao.bloqueio && (
        <div className="text-muted">As mensagens de cadência para esta conta são canceladas automaticamente.</div>
      )}
      {situacao.escrita_disponivel && (
        <Button size="sm" variant="ghost" className="self-start" disabled={enviando} onClick={enviar}>
          {enviando ? "Enviando…" : "Enviar ao CRM"}
        </Button>
      )}
      {mensagem && <div className="text-muted">{mensagem}</div>}
    </div>
  );
}
