import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";

import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { api, ApiError } from "@/lib/api";

export function EsqueciSenha() {
  const [email, setEmail] = useState("");
  const [enviado, setEnviado] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [carregando, setCarregando] = useState(false);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setErro(null);
    setCarregando(true);
    try {
      await api.post("/auth/esqueci-senha", { email });
      setEnviado(true);
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível enviar o link de redefinição.");
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
          <div className="mt-1 text-[11px] text-muted">Esqueci minha senha</div>
        </div>

        {enviado ? (
          <div className="text-center text-[12px] text-text">
            Se esse e-mail estiver cadastrado, você vai receber um link para redefinir sua senha em instantes.
            Confira também a caixa de spam.
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="flex flex-col gap-3">
            <div>
              <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">E-mail</div>
              <Input
                type="email"
                required
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                placeholder="voce@empresa.com.br"
              />
            </div>

            {erro && <div className="text-[12px] text-red">{erro}</div>}

            <Button type="submit" disabled={carregando} className="mt-1 w-full justify-center">
              {carregando ? "Enviando..." : "Enviar link de redefinição"}
            </Button>
          </form>
        )}

        <div className="mt-5 text-center text-[11px] text-muted">
          <Link to="/login" className="text-cyan hover:underline">
            Voltar para o login
          </Link>
        </div>
      </Card>
    </div>
  );
}
