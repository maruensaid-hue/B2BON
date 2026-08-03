import { useEffect, useState, type FormEvent } from "react";

import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Modal } from "@/components/ui/Modal";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";

interface Mensagem {
  id: number;
  tenant_id_remetente: string;
  tenant_id_destinatario: string;
  texto: string;
  lida_em: string | null;
  criado_em: string;
}

interface Props {
  tenantId: string;
  nomeExibicao: string;
  onClose: () => void;
}

export function ConversaModal({ tenantId, nomeExibicao, onClose }: Props) {
  const { usuario } = useAuth();
  const [mensagens, setMensagens] = useState<Mensagem[]>([]);
  const [erro, setErro] = useState<string | null>(null);

  async function carregar() {
    try {
      const resposta = await api.get<Mensagem[]>(`/rede-social/mensagens/${tenantId}`);
      setMensagens(resposta);
      await Promise.all(
        resposta
          .filter((mensagem) => mensagem.lida_em === null && mensagem.tenant_id_destinatario === usuario?.tenant_id)
          .map((mensagem) => api.post(`/rede-social/mensagens/${mensagem.id}/marcar-lida`)),
      );
    } catch {
      setErro("Não foi possível carregar a conversa.");
    }
  }

  useEffect(() => {
    carregar();
  }, [tenantId]);

  async function enviar(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const texto = String(form.get("texto") ?? "").trim();
    if (!texto) return;
    try {
      await api.post("/rede-social/mensagens", { tenant_id_destinatario: tenantId, texto });
      event.currentTarget.reset();
      await carregar();
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível enviar a mensagem.");
    }
  }

  return (
    <Modal title={`Conversa — ${nomeExibicao}`} open onClose={onClose}>
      {erro && <div className="mb-3 text-[12px] text-red">{erro}</div>}

      <div className="mb-3 flex max-h-80 flex-col gap-2 overflow-y-auto">
        {mensagens.map((mensagem) => {
          const enviadaPorMim = mensagem.tenant_id_remetente === usuario?.tenant_id;
          return (
            <div
              key={mensagem.id}
              className={`max-w-[80%] rounded-lg px-3 py-2 text-[12px] ${
                enviadaPorMim ? "self-end bg-cyan/15 text-text" : "self-start bg-surf2 text-text"
              }`}
            >
              {mensagem.texto}
            </div>
          );
        })}
        {mensagens.length === 0 && <div className="text-[12px] text-muted">Nenhuma mensagem ainda.</div>}
      </div>

      <form onSubmit={enviar} className="flex gap-2">
        <Input name="texto" placeholder="Escreva uma mensagem..." className="flex-1" />
        <Button type="submit" size="sm">
          Enviar
        </Button>
      </form>
    </Modal>
  );
}
