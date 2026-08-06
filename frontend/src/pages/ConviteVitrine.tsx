import { useState, type FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";

export function ConviteVitrine() {
  const { codigo } = useParams<{ codigo: string }>();
  const { registrarVitrine } = useAuth();
  const navigate = useNavigate();
  const [erro, setErro] = useState<string | null>(null);
  const [carregando, setCarregando] = useState(false);
  const [aceiteTermos, setAceiteTermos] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!codigo) return;
    setErro(null);
    setCarregando(true);
    const form = new FormData(event.currentTarget);
    try {
      await registrarVitrine({
        codigo_convite: codigo,
        razao_social: String(form.get("razao_social")),
        cnpj: String(form.get("cnpj") || "") || undefined,
        nome_admin: String(form.get("nome_admin")),
        email_admin: String(form.get("email_admin")),
        senha_admin: String(form.get("senha_admin")),
        aceite_termos: aceiteTermos,
      });
      navigate("/rede-social", { replace: true });
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível aceitar o convite.");
    } finally {
      setCarregando(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center p-4">
      <Card glow className="w-full max-w-sm">
        <div className="mb-6 text-center">
          <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-xl bg-gradient-to-br from-cyan to-[#005F7A] font-head text-2xl font-black text-bg">
            B
          </div>
          <div className="font-head text-lg font-extrabold">
            B2B <span className="text-cyan">ON</span>
          </div>
          <div className="mt-1 text-[11px] text-muted">
            Entre na Rede Social — conecte-se com outras empresas e conheça o CRM, o MAP e o PREDATOR.
          </div>
        </div>

        <form onSubmit={handleSubmit} className="flex flex-col gap-3">
          <div>
            <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">Razão social</div>
            <Input name="razao_social" required placeholder="Sua Empresa Ltda" />
          </div>
          <div>
            <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">CNPJ (opcional)</div>
            <Input name="cnpj" placeholder="00.000.000/0001-00" />
          </div>
          <div>
            <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">Seu nome</div>
            <Input name="nome_admin" required placeholder="Como você se chama" />
          </div>
          <div>
            <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">E-mail</div>
            <Input name="email_admin" type="email" required placeholder="voce@empresa.com.br" />
          </div>
          <div>
            <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">Senha</div>
            <Input name="senha_admin" type="password" required minLength={8} placeholder="Mínimo 8 caracteres" />
          </div>

          <label className="flex items-start gap-2 text-[11px] text-muted">
            <input
              type="checkbox"
              className="mt-0.5"
              checked={aceiteTermos}
              onChange={(event) => setAceiteTermos(event.target.checked)}
            />
            <span>
              Li e aceito a{" "}
              <Link to="/privacidade" target="_blank" className="text-cyan hover:underline">
                Política de Privacidade
              </Link>{" "}
              e os{" "}
              <Link to="/termos" target="_blank" className="text-cyan hover:underline">
                Termos de Uso
              </Link>
              .
            </span>
          </label>

          {erro && <div className="text-[12px] text-red">{erro}</div>}

          <Button type="submit" disabled={carregando || !aceiteTermos} className="mt-1 w-full justify-center">
            {carregando ? "Entrando..." : "Entrar na Rede Social"}
          </Button>
        </form>
      </Card>
    </div>
  );
}
