import { useCallback, useEffect, useState, type FormEvent } from "react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Input, Select } from "@/components/ui/Input";
import { api, ApiError } from "@/lib/api";
import { ConexaoEscrita } from "@/pages/admin/ConexaoEscrita";

export interface ConectorHub {
  sistema: string;
  nome: string;
  status: "AVAILABLE" | "BETA" | "COMING_SOON";
  descricao: string;
  conectavel: boolean;
  /** D-087: "Conectar com 1 clique" disponível (app OAuth da B2B ON configurado). */
  oauth?: boolean;
  /** D-087: o conector escreve no CRM (PREDATOR/MAP → CRM). */
  escrita?: boolean;
}

interface Conexao {
  id: number;
  sistema: string;
  nome: string;
  status: string;
  configuracao: Record<string, string>;
  ultimo_sync_em: string | null;
  ultimo_erro: string | null;
}

interface Campo {
  nome: string;
  rotulo: string;
  segredo?: boolean;
  obrigatorio?: boolean;
  configuracao?: boolean;
}

/** Campos pedidos por conector (Fase 13). Segredos vão para o backend,
 * que grava criptografado e nunca devolve. */
const CAMPOS: Record<string, Campo[]> = {
  salesforce: [
    {
      nome: "instance_url",
      rotulo: "Instance URL (https://sua-org.my.salesforce.com)",
      obrigatorio: true,
    },
    { nome: "access_token", rotulo: "Access token", segredo: true },
    {
      nome: "refresh_token",
      rotulo: "Refresh token (opcional)",
      segredo: true,
    },
    {
      nome: "client_id",
      rotulo: "Client ID do Connected App (com refresh token)",
    },
    {
      nome: "client_secret",
      rotulo: "Client secret (opcional)",
      segredo: true,
    },
    {
      nome: "campo_cnpj",
      rotulo: "Campo de CNPJ na Account (ex.: CNPJ__c)",
      configuracao: true,
    },
    {
      nome: "moeda",
      rotulo: "Moeda dos valores (padrão BRL)",
      configuracao: true,
    },
    {
      nome: "campo_nps",
      rotulo: "Campo de NPS na Account (opcional, ex.: NPS__c)",
      configuracao: true,
    },
  ],
  hubspot: [
    {
      nome: "access_token",
      rotulo: "Access token (Private App ou OAuth)",
      segredo: true,
    },
    {
      nome: "refresh_token",
      rotulo: "Refresh token (app OAuth, opcional)",
      segredo: true,
    },
    { nome: "client_id", rotulo: "Client ID (app OAuth)" },
    {
      nome: "client_secret",
      rotulo: "Client secret (app OAuth)",
      segredo: true,
    },
    {
      nome: "campo_cnpj",
      rotulo: "Propriedade de CNPJ da empresa (ex.: cnpj)",
      configuracao: true,
    },
    {
      nome: "moeda",
      rotulo: "Moeda padrão (quando o negócio não informa)",
      configuracao: true,
    },
    {
      nome: "campo_nps",
      rotulo: "Propriedade de NPS da empresa (opcional)",
      configuracao: true,
    },
  ],
  pipedrive: [
    {
      nome: "api_token",
      rotulo: "API token (Configurações pessoais → API)",
      segredo: true,
      obrigatorio: true,
    },
    {
      nome: "campo_cnpj",
      rotulo: "Chave do campo de CNPJ da organização",
      configuracao: true,
    },
    {
      nome: "campo_nps",
      rotulo: "Chave do campo de NPS da organização (opcional)",
      configuracao: true,
    },
  ],
  rd_station: [
    {
      nome: "token",
      rotulo: "Token da instância (Perfil → Token)",
      segredo: true,
      obrigatorio: true,
    },
    {
      nome: "campo_cnpj",
      rotulo: "Id do campo personalizado de CNPJ",
      configuracao: true,
    },
    {
      nome: "moeda",
      rotulo: "Moeda dos valores (padrão BRL)",
      configuracao: true,
    },
    {
      nome: "campo_nps",
      rotulo: "Id do campo personalizado de NPS (opcional)",
      configuracao: true,
    },
  ],
};

const ENTIDADES = [
  "accounts",
  "organizations",
  "people",
  "opportunities",
  "customers",
  "activities",
];

function separar(form: FormData, campos: Campo[]) {
  const credenciais: Record<string, string> = {};
  const configuracao: Record<string, string> = {};
  for (const campo of campos) {
    const valor = String(form.get(campo.nome) ?? "").trim();
    if (valor)
      (campo.configuracao ? configuracao : credenciais)[campo.nome] = valor;
  }
  return { credenciais, configuracao };
}

/** Conexões com CRMs externos (Integration Hub, Fase 13). */
export function ConexoesCrm({ conectores }: { conectores: ConectorHub[] }) {
  const conectaveis = conectores.filter(
    (c) => c.conectavel && CAMPOS[c.sistema],
  );
  const [conexoes, setConexoes] = useState<Conexao[]>([]);
  const [sistema, setSistema] = useState<string>("");
  const [reconectando, setReconectando] = useState<number | null>(null);
  const [mensagem, setMensagem] = useState<string | null>(null);
  const [escritaAberta, setEscritaAberta] = useState<number | null>(null);
  const comOauth = conectores.filter((c) => c.conectavel && c.oauth);

  const carregar = useCallback(async () => {
    try {
      setConexoes(await api.get<Conexao[]>("/hub-integracoes/conexoes"));
    } catch {
      setMensagem("Não foi possível carregar as conexões.");
    }
  }, []);

  useEffect(() => {
    carregar();
  }, [carregar]);

  // D-087: volta do CRM depois do "Conectar com 1 clique". A conexão só é
  // criada aqui, com o login de quem iniciou (anti-CSRF no backend).
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const referencia = params.get("oauth");
    const falha = params.get("oauth_erro");
    if (!referencia && !falha) return;
    window.history.replaceState(null, "", window.location.pathname);
    if (falha) {
      setMensagem(falha);
      return;
    }
    api
      .post("/hub-integracoes/oauth/concluir", { referencia })
      .then(async () => {
        setMensagem("CRM conectado.");
        await carregar();
      })
      .catch((error) =>
        setMensagem(error instanceof ApiError ? error.message : "Não foi possível concluir a conexão."),
      );
  }, [carregar]);

  async function conectarUmClique(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const alvo = String(form.get("sistema_oauth"));
    try {
      const { url } = await api.post<{ url: string }>(`/hub-integracoes/oauth/${alvo}/iniciar`, {
        nome: String(form.get("nome_oauth") || alvo),
        escrita: form.get("escrita_oauth") === "on",
        sandbox: form.get("sandbox_oauth") === "on",
      });
      window.location.assign(url);
    } catch (error) {
      setMensagem(error instanceof ApiError ? error.message : "Não foi possível iniciar a conexão.");
    }
  }

  const escolhido = sistema || conectaveis[0]?.sistema || "";

  async function conectar(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formulario = event.currentTarget;
    const form = new FormData(formulario);
    try {
      await api.post("/hub-integracoes/conexoes", {
        sistema: escolhido,
        nome: String(form.get("nome")),
        ...separar(form, CAMPOS[escolhido] ?? []),
      });
      formulario.reset();
      setMensagem("Conexão criada.");
      await carregar();
    } catch (error) {
      setMensagem(
        error instanceof ApiError
          ? error.message
          : "Não foi possível conectar.",
      );
    }
  }

  async function reconectar(
    event: FormEvent<HTMLFormElement>,
    conexao: Conexao,
  ) {
    event.preventDefault();
    const campos = (CAMPOS[conexao.sistema] ?? []).filter(
      (c) => !c.configuracao,
    );
    try {
      await api.put(`/hub-integracoes/conexoes/${conexao.id}/credenciais`, {
        credenciais: separar(new FormData(event.currentTarget), campos)
          .credenciais,
      });
      setReconectando(null);
      setMensagem("Credenciais atualizadas.");
      await carregar();
    } catch (error) {
      setMensagem(
        error instanceof ApiError
          ? error.message
          : "Não foi possível reconectar.",
      );
    }
  }

  async function sincronizar(conexao: Conexao, entidade: string) {
    try {
      const execucao = await api.post<{
        status: string;
        itens_lidos: number;
        erro: string | null;
      }>(`/hub-integracoes/conexoes/${conexao.id}/sincronizar/${entidade}`);
      setMensagem(
        execucao.status === "sucesso"
          ? `${entidade}: ${execucao.itens_lidos} registro(s) lido(s).`
          : `${entidade}: falhou — ${execucao.erro ?? "erro desconhecido"}`,
      );
      await carregar();
    } catch (error) {
      setMensagem(
        error instanceof ApiError
          ? error.message
          : "Não foi possível sincronizar.",
      );
    }
  }

  return (
    <div
      className="mt-3 flex flex-col gap-2 text-[12px]"
      data-testid="conexoes-crm"
    >
      {mensagem && <div className="text-muted">{mensagem}</div>}
      {conexoes.map((conexao) => (
        <div key={conexao.id} className="rounded-lg border border-border p-3">
          <div className="flex items-center justify-between gap-2">
            <span className="font-semibold">
              {conexao.nome}{" "}
              <span className="text-muted">· {conexao.sistema}</span>
            </span>
            <Badge tone={conexao.status === "ativa" ? "muted" : "red"}>
              {conexao.status}
            </Badge>
          </div>
          <div className="mt-1 text-muted">
            Último sync:{" "}
            {conexao.ultimo_sync_em
              ? new Date(conexao.ultimo_sync_em).toLocaleString("pt-BR")
              : "nunca"}
            {conexao.ultimo_erro && (
              <span className="text-red"> · {conexao.ultimo_erro}</span>
            )}
          </div>
          <div className="mt-1.5 flex flex-wrap gap-1.5">
            {ENTIDADES.map((entidade) => (
              <Button
                key={entidade}
                size="sm"
                variant="ghost"
                onClick={() => sincronizar(conexao, entidade)}
              >
                Sync {entidade}
              </Button>
            ))}
            {CAMPOS[conexao.sistema] && (
              <Button
                size="sm"
                variant="ghost"
                onClick={() => setReconectando(conexao.id)}
              >
                Reconectar
              </Button>
            )}
            {conectores.find((c) => c.sistema === conexao.sistema)?.escrita && (
              <Button
                size="sm"
                variant="ghost"
                onClick={() =>
                  setEscritaAberta(escritaAberta === conexao.id ? null : conexao.id)
                }
                data-testid="abrir-escrita"
              >
                {escritaAberta === conexao.id ? "Fechar escrita no CRM" : "Escrita no CRM"}
              </Button>
            )}
          </div>
          {escritaAberta === conexao.id && (
            <ConexaoEscrita
              conexaoId={conexao.id}
              pausada={conexao.status === "pausada"}
              aoMudar={carregar}
            />
          )}
          {reconectando === conexao.id && (
            <form
              onSubmit={(e) => reconectar(e, conexao)}
              className="mt-2 flex flex-col gap-1.5"
            >
              {(CAMPOS[conexao.sistema] ?? [])
                .filter((c) => !c.configuracao)
                .map((campo) => (
                  <Input
                    key={campo.nome}
                    name={campo.nome}
                    type={campo.segredo ? "password" : "text"}
                    placeholder={campo.rotulo}
                    required={campo.obrigatorio}
                    autoComplete="off"
                  />
                ))}
              <Button type="submit" size="sm" className="self-start">
                Salvar credenciais
              </Button>
            </form>
          )}
        </div>
      ))}

      {comOauth.length > 0 && (
        <form
          onSubmit={conectarUmClique}
          className="flex flex-col gap-1.5 rounded-lg border border-border p-3"
          data-testid="conectar-oauth"
        >
          <div className="font-semibold">Conectar com 1 clique</div>
          <div className="flex flex-wrap gap-2">
            <Select name="sistema_oauth" className="w-44" aria-label="CRM">
              {comOauth.map((c) => (
                <option key={c.sistema} value={c.sistema}>
                  {c.nome}
                </option>
              ))}
            </Select>
            <Input name="nome_oauth" placeholder="Nome da conexão" className="flex-1" />
          </div>
          <label className="flex items-center gap-2">
            <input type="checkbox" name="escrita_oauth" />
            Pedir permissão de escrita (para PREDATOR/MAP → CRM; a escrita continua desligada até você ligar)
          </label>
          <label className="flex items-center gap-2">
            <input type="checkbox" name="sandbox_oauth" />
            Salesforce sandbox (test.salesforce.com)
          </label>
          <Button type="submit" size="sm" className="self-start">
            Conectar
          </Button>
        </form>
      )}

      {conectaveis.length > 0 && (
        <form
          onSubmit={conectar}
          className="flex flex-col gap-1.5 rounded-lg border border-border p-3"
        >
          <div className="flex gap-2">
            <Select
              value={escolhido}
              onChange={(e) => setSistema(e.target.value)}
              className="w-44"
            >
              {conectaveis.map((c) => (
                <option key={c.sistema} value={c.sistema}>
                  {c.nome}
                </option>
              ))}
            </Select>
            <Input
              name="nome"
              required
              placeholder="Nome da conexão"
              className="flex-1"
            />
          </div>
          {(CAMPOS[escolhido] ?? []).map((campo) => (
            <Input
              key={`${escolhido}-${campo.nome}`}
              name={campo.nome}
              type={campo.segredo ? "password" : "text"}
              placeholder={campo.rotulo}
              required={campo.obrigatorio}
              autoComplete="off"
            />
          ))}
          <Button type="submit" size="sm" className="self-start">
            Conectar
          </Button>
        </form>
      )}
    </div>
  );
}
