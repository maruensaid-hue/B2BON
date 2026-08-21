import { useEffect, useState, type FormEvent } from "react";
import { Link, useParams } from "react-router-dom";

import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";

interface Plano {
  id: number;
  nome: string;
  franquia_contas_mes: number;
  max_usuarios: number;
  preco_mensal: number;
}

interface InfoConvite {
  status: string;
  gratuito: boolean;
}

export function ConviteVitrine() {
  const { codigo } = useParams<{ codigo: string }>();
  const { registrarVitrine } = useAuth();
  const [erro, setErro] = useState<string | null>(null);
  const [carregando, setCarregando] = useState(false);
  const [aceiteTermos, setAceiteTermos] = useState(false);
  const [planos, setPlanos] = useState<Plano[]>([]);
  const [planoId, setPlanoId] = useState<number | null>(null);
  const [info, setInfo] = useState<InfoConvite | null>(null);

  useEffect(() => {
    if (!codigo) return;
    api
      .get<InfoConvite>(`/convites/vitrine/${codigo}/info`)
      .then((resposta) => {
        setInfo(resposta);
        if (resposta.status !== "disponivel" || resposta.gratuito) return;
        return api.get<Plano[]>("/planos?apenas_self_service=true").then((planosResp) => {
          setPlanos(planosResp);
          if (planosResp.length > 0) setPlanoId(planosResp[0].id);
        });
      })
      .catch(() => setErro("Este link de convite não é mais válido."));
  }, [codigo]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!codigo) return;
    if (!info?.gratuito && planoId === null) return;
    setErro(null);
    setCarregando(true);
    const form = new FormData(event.currentTarget);
    try {
      const checkoutUrl = await registrarVitrine({
        codigo_convite: codigo,
        razao_social: String(form.get("razao_social")),
        cnpj: String(form.get("cnpj") || "") || undefined,
        nome_admin: String(form.get("nome_admin")),
        email_admin: String(form.get("email_admin")),
        senha_admin: String(form.get("senha_admin")),
        aceite_termos: aceiteTermos,
        plano_id: info?.gratuito ? undefined : planoId ?? undefined,
      });
      if (checkoutUrl) {
        window.location.href = checkoutUrl;
      } else {
        window.location.href = "/rede-social";
      }
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível aceitar o convite.");
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

  if (info && info.status !== "disponivel") {
    const mensagens: Record<string, string> = {
      usado: "Este convite já foi utilizado.",
      revogado: "Este convite foi revogado por quem o enviou.",
      expirado: "Este convite expirou.",
    };
    return (
      <div className="flex min-h-screen items-center justify-center p-4">
        <Card glow className="w-full max-w-md text-center text-[13px] text-muted">
          {mensagens[info.status] ?? "Este convite não está mais disponível."}
        </Card>
      </div>
    );
  }

  return (
    <div className="flex min-h-screen items-center justify-center p-4">
      <Card glow className="w-full max-w-md">
        <div className="mb-6 text-center">
          <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-xl bg-gradient-to-br from-cyan to-[#005F7A] font-head text-2xl font-black text-bg">
            B
          </div>
          <div className="font-head text-lg font-extrabold">
            B2B <span className="text-cyan">ON</span>
          </div>
          <div className="mt-1 text-[11px] text-muted">
            {info?.gratuito
              ? "Cadastre sua empresa e comece a usar o plano de teste gratuito, sem cartão de crédito."
              : "Cadastre sua empresa, escolha um plano e comece a usar CRM, MAP e PREDATOR."}
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

          {info?.gratuito ? (
            <div className="rounded-lg border border-cyan/40 bg-cyan/10 px-3 py-2 text-[12px]">
              <div className="font-semibold text-cyan">Plano de teste gratuito</div>
              <div className="text-[10.5px] text-muted">Sem custo, sem cartão de crédito — acesso liberado na hora.</div>
            </div>
          ) : (
            <div>
              <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">Escolha um plano</div>
              <div className="flex flex-col gap-2">
                {planos.map((plano) => (
                  <button
                    key={plano.id}
                    type="button"
                    onClick={() => setPlanoId(plano.id)}
                    className={`flex items-center justify-between rounded-lg border px-3 py-2 text-left text-[12px] transition-colors ${
                      planoId === plano.id ? "border-cyan bg-cyan/10" : "border-border hover:bg-surf2"
                    }`}
                  >
                    <div>
                      <div className="font-semibold">{plano.nome}</div>
                      <div className="text-[10.5px] text-muted">
                        Até {plano.max_usuarios} usuários · {plano.franquia_contas_mes} contas/mês
                      </div>
                    </div>
                    <div className="font-head text-[13px] font-bold text-cyan">
                      R${plano.preco_mensal.toFixed(0)}
                      <span className="text-[9.5px] font-normal text-muted">/mês</span>
                    </div>
                  </button>
                ))}
                {planos.length === 0 && !erro && (
                  <div className="text-[11px] text-muted">Carregando planos...</div>
                )}
              </div>
            </div>
          )}

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

          <Button
            type="submit"
            disabled={carregando || !aceiteTermos || (!info?.gratuito && planoId === null)}
            className="mt-1 w-full justify-center"
          >
            {info?.gratuito
              ? carregando
                ? "Criando sua conta..."
                : "Criar minha conta grátis"
              : carregando
                ? "Indo para o pagamento..."
                : "Continuar para o pagamento"}
          </Button>
        </form>
      </Card>
    </div>
  );
}
