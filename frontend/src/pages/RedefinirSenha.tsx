import { useState, type FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { api, ApiError } from "@/lib/api";

export function RedefinirSenha() {
  const { token } = useParams<{ token: string }>();
  const navigate = useNavigate();
  const [novaSenha, setNovaSenha] = useState("");
  const [confirmarSenha, setConfirmarSenha] = useState("");
  const [erro, setErro] = useState<string | null>(null);
  const [carregando, setCarregando] = useState(false);
  const [sucesso, setSucesso] = useState(false);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (!token) return;
    setErro(null);
    if (novaSenha !== confirmarSenha) {
      setErro("As senhas não coincidem.");
      return;
    }
    setCarregando(true);
    try {
      await api.post("/auth/redefinir-senha", { token, nova_senha: novaSenha });
      setSucesso(true);
      setTimeout(() => navigate("/login", { replace: true }), 2500);
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível redefinir a senha.");
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
          <div className="mt-1 text-[11px] text-muted">Criar uma senha nova</div>
        </div>

        {sucesso ? (
          <div className="text-center text-[12px] text-text">
            Senha redefinida com sucesso! Levando você para o login...
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="flex flex-col gap-3">
            <div>
              <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">Nova senha</div>
              <Input
                type="password"
                required
                minLength={8}
                value={novaSenha}
                onChange={(event) => setNovaSenha(event.target.value)}
                placeholder="Mínimo 8 caracteres"
              />
            </div>
            <div>
              <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">Confirmar nova senha</div>
              <Input
                type="password"
                required
                minLength={8}
                value={confirmarSenha}
                onChange={(event) => setConfirmarSenha(event.target.value)}
                placeholder="Repita a senha"
              />
            </div>

            {erro && <div className="text-[12px] text-red">{erro}</div>}

            <Button type="submit" disabled={carregando} className="mt-1 w-full justify-center">
              {carregando ? "Salvando..." : "Redefinir senha"}
            </Button>
          </form>
        )}

        {!sucesso && (
          <div className="mt-5 text-center text-[11px] text-muted">
            <Link to="/login" className="text-cyan hover:underline">
              Voltar para o login
            </Link>
          </div>
        )}
      </Card>
    </div>
  );
}
