import { useEffect, useRef, useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";

import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";

// Google Identity Services (GSI) — SDK carregado sob demanda (só quando
// há um Client ID configurado, ver useEffect abaixo). Tipagem mínima só
// do que este arquivo usa, sem instalar @types/google.accounts inteiro.
declare global {
  interface Window {
    google?: {
      accounts: {
        id: {
          initialize: (config: { client_id: string; callback: (resposta: { credential: string }) => void }) => void;
          renderButton: (pai: HTMLElement, opcoes: Record<string, unknown>) => void;
        };
      };
    };
  }
}

const GOOGLE_CLIENT_ID = import.meta.env.VITE_GOOGLE_OAUTH_CLIENT_ID as string | undefined;

export function Login() {
  const { entrar, entrarComGoogle } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [senha, setSenha] = useState("");
  const [erro, setErro] = useState<string | null>(null);
  const [carregando, setCarregando] = useState(false);
  const [mostrarCadastro, setMostrarCadastro] = useState(false);
  const [codigoConvite, setCodigoConvite] = useState("");
  const botaoGoogleRef = useRef<HTMLDivElement>(null);

  // Sem Client ID configurado, mantém o botão desabilitado de sempre
  // (mesmo aviso, sem apontar mais pra "Onda F2" — interno demais pra
  // quem vê a tela). Com Client ID, carrega o SDK do Google e troca
  // pelo botão de verdade — o próprio Google renderiza o botão dentro
  // de um iframe (não dá pra restilizar), então o fallback continua
  // sendo o visual "ghost" já usado no resto da tela.
  useEffect(() => {
    if (!GOOGLE_CLIENT_ID) return;
    let cancelado = false;

    async function handleCredentialResponse(resposta: { credential: string }) {
      setErro(null);
      setCarregando(true);
      try {
        await entrarComGoogle(resposta.credential);
        navigate("/", { replace: true });
      } catch (error) {
        setErro(error instanceof ApiError ? error.message : "Não foi possível entrar com o Google.");
      } finally {
        setCarregando(false);
      }
    }

    function inicializar() {
      if (cancelado || !window.google || !botaoGoogleRef.current) return;
      window.google.accounts.id.initialize({ client_id: GOOGLE_CLIENT_ID!, callback: handleCredentialResponse });
      window.google.accounts.id.renderButton(botaoGoogleRef.current, {
        theme: "outline",
        size: "large",
        width: 320,
        text: "continue_with",
      });
    }

    if (window.google) {
      inicializar();
      return;
    }
    const script = document.createElement("script");
    script.src = "https://accounts.google.com/gsi/client";
    script.async = true;
    script.defer = true;
    script.onload = inicializar;
    document.head.appendChild(script);
    return () => {
      cancelado = true;
    };
  }, [entrarComGoogle, navigate]);

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
            <div className="mb-1.5 flex items-center justify-between">
              <div className="text-[10px] tracking-wide text-muted uppercase">Senha</div>
              <Link to="/esqueci-senha" className="text-[10px] text-cyan hover:underline">
                Esqueci minha senha
              </Link>
            </div>
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

        {GOOGLE_CLIENT_ID ? (
          <div ref={botaoGoogleRef} className="mt-4 flex w-full justify-center" />
        ) : (
          <Button
            variant="ghost"
            className="mt-4 w-full justify-center"
            onClick={() => setErro("Login com Google ainda não está configurado nesta plataforma.")}
          >
            Entrar com Google
          </Button>
        )}

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
