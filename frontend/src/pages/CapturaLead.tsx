import { useEffect, useState, type FormEvent } from "react";
import { useParams } from "react-router-dom";

import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { api, ApiError } from "@/lib/api";

interface InfoCapturaLead {
  nome_exibicao: string;
}

/** Página pública de captura de lead (sem login) — link permanente por
 * tenant, pensado pra CTA de anúncio (Instagram, site) redirecionar aqui.
 * Ao submeter, cai como prospect direto no CRM do tenant dono do link,
 * mesmo padrão visual de `ConviteVitrine.tsx`. */
export function CapturaLead() {
  const { codigo } = useParams<{ codigo: string }>();
  const [info, setInfo] = useState<InfoCapturaLead | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [carregando, setCarregando] = useState(false);
  const [enviado, setEnviado] = useState(false);

  useEffect(() => {
    if (!codigo) return;
    api
      .get<InfoCapturaLead>(`/captura-lead/${codigo}/info`)
      .catch(() => null)
      .then((resposta) => {
        if (resposta) setInfo(resposta);
        else setErro("Este link não é mais válido.");
      });
  }, [codigo]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!codigo) return;
    setErro(null);
    setCarregando(true);
    const form = new FormData(event.currentTarget);
    try {
      await api.post(`/captura-lead/${codigo}`, {
        nome_empresa: String(form.get("nome_empresa")),
        cnpj: String(form.get("cnpj") || "") || undefined,
        nome_contato: String(form.get("nome_contato")),
        email_contato: String(form.get("email_contato")),
        telefone_contato: String(form.get("telefone_contato") || "") || undefined,
        cargo_contato: String(form.get("cargo_contato") || "") || undefined,
      });
      setEnviado(true);
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível enviar seus dados agora.");
    } finally {
      setCarregando(false);
    }
  }

  if (erro && !info) {
    return (
      <div className="flex min-h-screen items-center justify-center p-4">
        <Card glow className="w-full max-w-md text-center text-[13px] text-muted">
          {erro}
        </Card>
      </div>
    );
  }

  if (enviado) {
    return (
      <div className="flex min-h-screen items-center justify-center p-4">
        <Card glow className="w-full max-w-md text-center">
          <div className="font-head text-lg font-extrabold text-cyan">Recebemos seu contato!</div>
          <div className="mt-2 text-[12.5px] text-muted">
            {info ? `A equipe da ${info.nome_exibicao}` : "A equipe"} vai entrar em contato em breve.
          </div>
        </Card>
      </div>
    );
  }

  return (
    <div className="flex min-h-screen items-center justify-center p-4">
      <Card glow className="w-full max-w-md">
        <div className="mb-6 text-center">
          <div className="font-head text-lg font-extrabold">
            Fale com {info ? info.nome_exibicao : "a gente"}
          </div>
          <div className="mt-1 text-[11px] text-muted">Preencha seus dados que retornamos em breve.</div>
        </div>

        <form onSubmit={handleSubmit} className="flex flex-col gap-3">
          <div>
            <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">Sua empresa</div>
            <Input name="nome_empresa" required placeholder="Nome da sua empresa" />
          </div>
          <div>
            <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">CNPJ (opcional)</div>
            <Input name="cnpj" placeholder="00.000.000/0001-00" />
          </div>
          <div>
            <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">Seu nome</div>
            <Input name="nome_contato" required placeholder="Como você se chama" />
          </div>
          <div>
            <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">Seu cargo (opcional)</div>
            <Input name="cargo_contato" placeholder="Ex.: Diretor comercial" />
          </div>
          <div>
            <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">E-mail</div>
            <Input name="email_contato" type="email" required placeholder="voce@empresa.com.br" />
          </div>
          <div>
            <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">Telefone (opcional)</div>
            <Input name="telefone_contato" placeholder="(11) 99999-9999" />
          </div>

          {erro && <div className="text-[12px] text-red">{erro}</div>}

          <Button type="submit" disabled={carregando} className="mt-1 w-full justify-center">
            {carregando ? "Enviando..." : "Enviar"}
          </Button>
        </form>
      </Card>
    </div>
  );
}
