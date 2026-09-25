import { useCallback, useEffect, useState, type FormEvent } from "react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Input, Select } from "@/components/ui/Input";
import { api, ApiError } from "@/lib/api";

export interface ConectorHub {
  sistema: string;
  nome: string;
  status: "AVAILABLE" | "BETA" | "COMING_SOON";
  descricao: string;
  conectavel: boolean;
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
          </div>
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
