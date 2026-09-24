import { useEffect, useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";

interface Plano {
  id: number;
  nome: string;
  franquia_contas_mes: number;
  max_usuarios: number | null;
  preco_mensal: number;
  limite_enriquecimento_site_semanal: number | null;
  limite_enriquecimento_contatos_semanal: number | null;
  limite_cadencias_mes: number | null;
  limite_campanhas_mes: number | null;
}

// Letras miúdas da janela de assinatura (raio-X 2026-09-22) — de
// propósito sem destaque (sem cor de aviso, fonte mínima): informa o
// que o plano restringe, sem parecer uma limitação agressiva no momento
// da escolha.
function formatarLimite(valor: number | null): string {
  return valor === null ? "sem limite" : String(valor);
}

/** Cadastro público sem convite (raio-X 2026-09-21, página de
 * boas-vindas) — quem não tem convite escolhe um plano pago aqui (o
 * plano Teste nunca aparece, é exclusivo de convite administrativo)
 * e já sai direto pro checkout. Mesmo padrão visual/de plano-picker de
 * `ConviteVitrine.tsx`, sem nenhum campo de código. */
export function CriarConta() {
  const { criarContaPublica } = useAuth();
  const [searchParams] = useSearchParams();
  const [erro, setErro] = useState<string | null>(null);
  const [carregando, setCarregando] = useState(false);
  const [aceiteTermos, setAceiteTermos] = useState(false);
  const [planos, setPlanos] = useState<Plano[]>([]);
  const [planoId, setPlanoId] = useState<number | null>(null);

  useEffect(() => {
    api
      .get<Plano[]>("/planos?apenas_self_service=true")
      .then((resposta) => {
        setPlanos(resposta);
        // Vem da página de Planos e Valores com o plano já escolhido
        // (`?plano=Professional`, por nome — mais estável no link do que
        // o id numérico) — cai no primeiro da lista se não bater com
        // nenhum nome (link direto sem esse parâmetro, ou nome digitado
        // errado em algum lugar).
        const nomeDesejado = searchParams.get("plano");
        const planoPreSelecionado = nomeDesejado
          ? resposta.find((plano) => plano.nome.toLowerCase() === nomeDesejado.toLowerCase())
          : undefined;
        if (planoPreSelecionado) setPlanoId(planoPreSelecionado.id);
        else if (resposta.length > 0) setPlanoId(resposta[0].id);
      })
      .catch(() => setErro("Não foi possível carregar os planos agora. Tente de novo em instantes."));
  }, [searchParams]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (planoId === null) return;
    setErro(null);
    setCarregando(true);
    const form = new FormData(event.currentTarget);
    try {
      const checkoutUrl = await criarContaPublica({
        razao_social: String(form.get("razao_social")),
        cnpj: String(form.get("cnpj") || "") || undefined,
        nome_admin: String(form.get("nome_admin")),
        email_admin: String(form.get("email_admin")),
        senha_admin: String(form.get("senha_admin")),
        aceite_termos: aceiteTermos,
        plano_id: planoId,
      });
      window.location.href = checkoutUrl ?? "/rede-social";
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível criar sua conta agora.");
      setCarregando(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center p-4">
      <Card glow className="w-full max-w-md">
        <div className="mb-6 text-center">
          <Link to="/" className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-xl bg-gradient-to-br from-cyan to-[#005F7A] font-head text-2xl font-black text-bg">
            B
          </Link>
          <div className="font-head text-lg font-extrabold">
            B2B <span className="text-cyan">ON</span>
          </div>
          <div className="mt-1 text-[11px] text-muted">
            Cadastre sua empresa, escolha um plano e comece a usar CRM, MAP e PREDATOR.
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

          <div>
            <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">Escolha um plano</div>
            <div className="flex flex-col gap-2">
              {planos.map((plano) => (
                <button
                  key={plano.id}
                  type="button"
                  onClick={() => setPlanoId(plano.id)}
                  className={`flex items-start justify-between gap-3 rounded-lg border px-3 py-2 text-left text-[12px] transition-colors ${
                    planoId === plano.id ? "border-cyan bg-cyan/10" : "border-border hover:bg-surf2"
                  }`}
                >
                  <div>
                    <div className="font-semibold">{plano.nome}</div>
                    <div className="text-[10.5px] text-muted">
                      {plano.max_usuarios != null ? `Até ${plano.max_usuarios} usuários` : "Usuários ilimitados"} ·{" "}
                      {plano.franquia_contas_mes} contas/mês
                    </div>
                    <div className="mt-1 text-[9px] leading-snug text-muted/70">
                      Limites do plano: {formatarLimite(plano.limite_enriquecimento_site_semanal)} pesquisas de site e{" "}
                      {formatarLimite(plano.limite_enriquecimento_contatos_semanal)} de contatos por semana ·{" "}
                      {formatarLimite(plano.limite_cadencias_mes)} cadências e{" "}
                      {formatarLimite(plano.limite_campanhas_mes)} campanhas por mês.
                    </div>
                  </div>
                  <div className="flex-shrink-0 font-head text-[13px] font-bold text-cyan">
                    R${plano.preco_mensal.toFixed(0)}
                    <span className="text-[9.5px] font-normal text-muted">/mês</span>
                  </div>
                </button>
              ))}
              {planos.length === 0 && !erro && <div className="text-[11px] text-muted">Carregando planos...</div>}
            </div>
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

          <Button type="submit" disabled={carregando || !aceiteTermos || planoId === null} className="mt-1 w-full justify-center">
            {carregando ? "Indo para o pagamento..." : "Continuar para o pagamento"}
          </Button>
        </form>

        <div className="mt-4 text-center text-[11px] text-muted">
          Já tem uma conta?{" "}
          <Link to="/login" className="text-cyan hover:underline">
            Fazer login
          </Link>
        </div>
      </Card>
    </div>
  );
}
