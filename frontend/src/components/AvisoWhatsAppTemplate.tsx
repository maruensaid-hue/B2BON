import { useState } from "react";

import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import { useAuth } from "@/lib/auth";

/** Aviso de que o WhatsApp é BYO por tenant e precisa de um template
 * aprovado pela Meta pro primeiro contato de qualquer cadência — sem
 * isso, a mensagem fica "adiada" silenciosamente (janela de 24h),
 * nunca chega a ser enviada, sem erro nenhum visível em lugar nenhum
 * da tela (raio-X 2026-09-14). Reaproveitado em Configuração e
 * Cadências — cada tenant precisa configurar a própria conta Meta,
 * isso não é feito uma vez só pra toda a plataforma. */
export function AvisoWhatsAppTemplate() {
  const { usuario, confirmarAvisoWhatsappTemplate } = useAuth();
  const [aberto, setAberto] = useState(true);
  const [naoMostrarMais, setNaoMostrarMais] = useState(false);
  const [salvando, setSalvando] = useState(false);

  if (usuario?.aviso_whatsapp_template_confirmado || !aberto) return null;

  async function fechar() {
    if (naoMostrarMais) {
      setSalvando(true);
      try {
        await confirmarAvisoWhatsappTemplate();
      } finally {
        setSalvando(false);
      }
    }
    setAberto(false);
  }

  return (
    <Modal title="WhatsApp Business — leia antes de mandar a primeira mensagem" open onClose={fechar}>
      <div className="flex flex-col gap-3 text-[12.5px]">
        <p>
          O WhatsApp é configurado por conta própria de cada cliente da B2B ON (a CyberFort não compartilha
          número com ninguém) — a conta Meta, o app e o token são seus.
        </p>
        <p>
          Além disso, a própria Meta exige um <b>template de mensagem aprovado</b> pra qualquer primeiro
          contato com um número que nunca falou com você antes. Sem template configurado no toque de
          WhatsApp, a mensagem fica <b>parada silenciosamente</b> — nenhum erro aparece em lugar nenhum da
          tela, ela simplesmente nunca sai.
        </p>
        <p>
          Depois que o contato responder (mesmo um "oi"), a janela de 24h abre e as mensagens seguintes
          daquela conversa podem ser texto livre normalmente.
        </p>
        <p className="text-muted">
          Veja o passo a passo completo (criar app na Meta, gerar token, cadastrar o template) no Manual do
          Usuário, seção WhatsApp Business.
        </p>
        <label className="mt-1 flex items-center gap-2">
          <input
            type="checkbox"
            checked={naoMostrarMais}
            onChange={(event) => setNaoMostrarMais(event.target.checked)}
          />
          Já configurei o WhatsApp Business e cadastrei um template aprovado — não mostrar este aviso de novo
        </label>
        <Button onClick={fechar} disabled={salvando} className="mt-1 w-full justify-center">
          {salvando ? "Salvando..." : "Fechar"}
        </Button>
      </div>
    </Modal>
  );
}
