import { useCallback, useEffect, useState, type FormEvent } from "react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Input, Select, Textarea } from "@/components/ui/Input";
import { api, ApiError } from "@/lib/api";

interface TemplateWhatsApp {
  id: number;
  nome: string;
  corpo: string;
  status: string;
}

const STATUS: Record<string, { rotulo: string; tom: "green" | "amber" | "red" | "muted" }> = {
  approved: { rotulo: "aprovado", tom: "green" },
  aprovado: { rotulo: "aprovado", tom: "green" },
  pending: { rotulo: "em análise na Meta", tom: "amber" },
  pendente: { rotulo: "em análise na Meta", tom: "amber" },
  in_appeal: { rotulo: "em recurso", tom: "amber" },
  rejected: { rotulo: "recusado", tom: "red" },
  rejeitado: { rotulo: "recusado", tom: "red" },
  paused: { rotulo: "pausado pela Meta", tom: "red" },
  disabled: { rotulo: "desativado pela Meta", tom: "red" },
};

/** Modelos de mensagem (templates) da conta do WhatsApp da empresa: lista com o status da Meta e criação pela própria plataforma. */
export function TemplatesWhatsApp({ conectado }: { conectado: boolean }) {
  const [templates, setTemplates] = useState<TemplateWhatsApp[]>([]);
  const [aberto, setAberto] = useState(false);
  const [nome, setNome] = useState("");
  const [categoria, setCategoria] = useState("UTILITY");
  const [corpo, setCorpo] = useState("");
  const [rodape, setRodape] = useState("");
  const [ocupado, setOcupado] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);

  const carregar = useCallback(async () => {
    setTemplates(await api.get<TemplateWhatsApp[]>("/whatsapp/templates"));
  }, []);

  useEffect(() => {
    if (conectado) carregar().catch(() => setTemplates([]));
  }, [conectado, carregar]);

  async function criar(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setErro(null);
    setAviso(null);
    setOcupado(true);
    try {
      const criado = await api.post<TemplateWhatsApp>("/whatsapp/templates", {
        nome,
        categoria,
        corpo,
        rodape: rodape.trim() || null,
      });
      setAviso(`Modelo "${criado.nome}" enviado para aprovação da Meta. O status atualiza aqui quando ela responder.`);
      setNome("");
      setCorpo("");
      setRodape("");
      setAberto(false);
      await carregar();
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível criar o modelo. Tente de novo.");
    } finally {
      setOcupado(false);
    }
  }

  if (!conectado) return null;

  return (
    <div className="mt-4 border-t border-border pt-4">
      <div className="mb-2 flex items-center justify-between">
        <div className="text-[10px] tracking-wide text-muted uppercase">Modelos de mensagem (templates)</div>
        <div className="flex gap-2">
          <Button type="button" size="sm" variant="ghost" onClick={() => carregar().catch(() => undefined)}>
            Atualizar status
          </Button>
          <Button type="button" size="sm" onClick={() => setAberto(!aberto)}>
            {aberto ? "Cancelar" : "Novo modelo"}
          </Button>
        </div>
      </div>

      {aberto && (
        <form onSubmit={criar} className="mb-3 flex flex-col gap-2 rounded-md border border-border p-3 text-[12px]">
          <div className="text-[11px] text-muted">
            O modelo é criado na conta do WhatsApp da sua empresa e vai para aprovação da Meta (costuma levar de minutos a algumas horas).
            Só modelos aprovados podem ser usados no primeiro contato das cadências e nas campanhas.
          </div>
          <Input label="Nome do modelo" value={nome} onChange={(e) => setNome(e.target.value)} placeholder="ex.: retorno_contato" required />
          <Select label="Categoria" value={categoria} onChange={(e) => setCategoria(e.target.value)}>
            <option value="UTILITY">Utilidade (lembrete, confirmação, retorno de algo combinado)</option>
            <option value="MARKETING">Marketing (oferta, apresentação, prospecção)</option>
          </Select>
          <Textarea
            label="Texto da mensagem"
            rows={4}
            value={corpo}
            maxLength={1024}
            onChange={(e) => setCorpo(e.target.value)}
            placeholder="Olá! Aqui é da equipe comercial. Podemos conversar sobre como reduzir o tempo de prospecção da sua empresa?"
            required
          />
          <div className="text-[11px] text-muted">
            Escreva o texto completo, sem variáveis como {"{{nome}}"}: o envio de modelos ainda não preenche variáveis. {corpo.length}/1024
          </div>
          <Input label="Rodapé (opcional)" value={rodape} maxLength={60} onChange={(e) => setRodape(e.target.value)} placeholder="Responda SAIR para não receber mais" />
          <div>
            <Button type="submit" disabled={ocupado || !nome.trim() || !corpo.trim()}>
              {ocupado ? "Enviando..." : "Enviar para aprovação da Meta"}
            </Button>
          </div>
        </form>
      )}

      {aviso && <div className="mb-2 text-[12px] text-green">{aviso}</div>}
      {erro && <div className="mb-2 text-[12px] text-red">{erro}</div>}

      {templates.length === 0 ? (
        <div className="text-[12px] text-muted">Nenhum modelo na conta ainda.</div>
      ) : (
        <div className="flex flex-col gap-1 text-[12px]">
          {templates.map((template) => {
            const status = STATUS[template.status] ?? { rotulo: template.status, tom: "muted" as const };
            return (
              <div key={template.id} className="border-b border-border py-1.5">
                <div className="flex items-center gap-2">
                  <span className="font-semibold text-text">{template.nome}</span>
                  <Badge tone={status.tom}>{status.rotulo}</Badge>
                </div>
                {template.corpo && <div className="mt-0.5 text-[11px] text-muted">{template.corpo}</div>}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
