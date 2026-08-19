import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";

import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";

export function Login() {
  const { entrar } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [senha, setSenha] = useState("");
  const [erro, setErro] = useState<string | null>(null);
  const [carregando, setCarregando] = useState(false);
  const [mostrarCadastro, setMostrarCadastro] = useState(false);
  const [codigoConvite, setCodigoConvite] = useState("");

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setErro(null);
    setCarregando(true);
    try {
      await entrar(email, senha);
      navigate("/", { replace: true });
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível entrar.");
    } finally {
      setCarregando(false);
    }
  }

  // O botão "Copiar link" (Rede Social) copia a URL inteira, não só o
  // código — colar o link inteiro aqui (em vez de abrir ele direto) é um
  // erro fácil de cometer, e sem isto virava uma URL duplicada
  // (/convite-vitrine/https://.../convite-vitrine/CODIGO) que nenhuma
  // rota reconhece, deixando a tela em branco sem nenhum aviso (raio-X
  // de produção real).
  function extrairCodigoConvite(valor: string): string {
    const texto = valor.trim();
    const correspondencia = texto.match(/convite-vitrine\/([^/?#\s]+)/);
    return correspondencia ? correspondencia[1] : texto;
  }

  function handleUsarCodigo(event: FormEvent) {
    event.preventDefault();
    const codigo = extrairCodigoConvite(codigoConvite);
    if (codigo) navigate(`/convite-vitrine/${codigo}`);
  }

  return (
    <div className="flex h-screen items-center justify-center p-4">
      <Card glow className="w-full max-w-sm">
        <div className="mb-6 text-center">
          <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-xl bg-gradient-to-br from-cyan to-[#005F7A] font-head text-2xl font-black text-bg">
            B
          </div>
          <div className="font-head text-lg font-extrabold">
            B2B <span className="text-cyan">ON</span>
          </div>
          <div className="text-[10px] tracking-widest text-muted">OPERATING NETWORK</div>
        </div>

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
          <div>
            <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">Senha</div>
            <Input
              type="password"
              required
              value={senha}
              onChange={(event) => setSenha(event.target.value)}
              placeholder="••••••••"
            />
          </div>

          {erro && <div className="text-[12px] text-red">{erro}</div>}

          <Button type="submit" disabled={carregando} className="mt-1 w-full justify-center">
            {carregando ? "Entrando..." : "Entrar"}
          </Button>
        </form>

        <div className="mt-4 flex items-center gap-2 text-[10px] text-muted">
          <div className="h-px flex-1 bg-border" />
          ou
          <div className="h-px flex-1 bg-border" />
        </div>

        <Button
          variant="ghost"
          className="mt-4 w-full justify-center"
          onClick={() => setErro("Login com Google ainda depende de configurar o Client ID OAuth (Onda F2).")}
        >
          Entrar com Google
        </Button>

        <div className="mt-4 text-center text-[11px] text-muted">
          Ainda não tem conta?{" "}
          <button
            type="button"
            className="text-cyan hover:underline"
            onClick={() => setMostrarCadastro((atual) => !atual)}
          >
            Tenho um código de convite
          </button>
        </div>

        {mostrarCadastro && (
          <form onSubmit={handleUsarCodigo} className="mt-3 flex flex-col gap-2">
            <Input
              value={codigoConvite}
              onChange={(event) => setCodigoConvite(event.target.value)}
              placeholder="Código do convite"
            />
            <Button type="submit" variant="ghost" className="w-full justify-center" disabled={!codigoConvite.trim()}>
              Continuar cadastro
            </Button>
          </form>
        )}

        <div className="mt-5 text-center text-[10px] text-muted">
          <Link to="/privacidade" className="hover:text-cyan hover:underline">
            Política de Privacidade
          </Link>
          {" · "}
          <Link to="/termos" className="hover:text-cyan hover:underline">
            Termos de Uso
          </Link>
        </div>
      </Card>
    </div>
  );
}
