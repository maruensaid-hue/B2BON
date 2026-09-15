import { useState, type FormEvent } from "react";

import { Button } from "@/components/ui/Button";
import { Card, SectionLabel } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";

export function Perfil() {
  const { usuario, atualizarWhatsappPessoal } = useAuth();
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [mensagem, setMensagem] = useState<string | null>(null);

  async function salvar(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (salvando) return;
    const form = new FormData(event.currentTarget);
    const whatsappPessoal = String(form.get("whatsapp_pessoal") ?? "").trim();
    setSalvando(true);
    setErro(null);
    setMensagem(null);
    try {
      await atualizarWhatsappPessoal(whatsappPessoal || null);
      setMensagem("Perfil salvo.");
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível salvar o perfil.");
    } finally {
      setSalvando(false);
    }
  }

  return (
    <div className="p-5.5">
      <div className="mb-5">
        <div className="font-head text-xl font-bold">Meu Perfil</div>
        <div className="mt-0.5 text-[11px] text-muted">Dados pessoais usados pela plataforma para te representar nas mensagens</div>
      </div>

      {erro && <div className="mb-4 text-[12px] text-red">{erro}</div>}
      {mensagem && <div className="mb-4 text-[12px] text-green">{mensagem}</div>}

      <Card>
        <SectionLabel>WhatsApp pessoal</SectionLabel>
        <div className="mb-3 text-[11px] text-muted">
          Usado como botão de redirecionamento nos templates de WhatsApp da cadência — quando o cliente
          responder pelo botão do template, ele vai direto para o seu WhatsApp de verdade (app do celular ou
          computador), não para dentro da plataforma. Sem esse número cadastrado, o botão do template não
          leva a lugar nenhum.
        </div>
        <form key={usuario?.whatsapp_pessoal ?? "vazio"} onSubmit={salvar} className="flex flex-col gap-3">
          <div>
            <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">Número (com DDI e DDD)</div>
            <Input
              name="whatsapp_pessoal"
              type="tel"
              defaultValue={usuario?.whatsapp_pessoal ?? ""}
              placeholder="+55 11 91234-5678"
            />
          </div>
          <Button type="submit" disabled={salvando} className="w-full justify-center">
            {salvando ? "Salvando..." : "Salvar"}
          </Button>
        </form>
      </Card>
    </div>
  );
}
