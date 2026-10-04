import { useCallback, useEffect, useState } from "react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Input, Select } from "@/components/ui/Input";
import { api, ApiError } from "@/lib/api";

interface Escrita {
  sistema: string;
  predator: boolean;
  map: boolean;
  deduplicar: boolean;
  pipeline_id: string | null;
  estagio_id: string | null;
  prazo_fechamento_dias: number | null;
  donos: Record<string, string>;
  campos: Record<string, string | null>;
  webhook_entrada_ativo: boolean;
}

interface Funil {
  id: string;
  nome: string;
  estagios: { id: string; nome: string }[];
}

interface Envio {
  id: number;
  operacao: string;
  status: string;
  tentativas: number;
  resultado: string | null;
  ultimo_erro: string | null;
  criado_em: string | null;
}

interface UsuarioResumo {
  id: number;
  nome: string;
}

const OPERACOES: Record<string, string> = {
  empresa: "Empresa",
  pessoa: "Contato",
  atividade_mensagem: "Mensagem enviada",
  reuniao_agendada: "Reunião → negócio",
  reuniao_resultado: "Resultado da reunião",
  optout: "Opt-out",
  sinais_conta: "Sinais do MAP",
};

const CAMPOS = [
  { chave: "score_risco", rotulo: "Campo do score de risco (MAP)" },
  { chave: "nivel_risco", rotulo: "Campo do nível de risco (MAP)" },
  { chave: "optout", rotulo: "Campo de opt-out do contato" },
] as const;

const CRIA_CAMPOS = new Set(["hubspot", "pipedrive"]);

function tomStatus(status: string): "green" | "red" | "amber" | "muted" {
  if (status === "enviado") return "green";
  if (status === "desistido") return "red";
  if (status === "pendente") return "amber";
  return "muted";
}

function erro(error: unknown, padrao: string) {
  return error instanceof ApiError ? error.message : padrao;
}

/** Escrita no CRM do cliente (D-087): opt-in por capacidade, funil/estágio,
 * donos, campos próprios da B2B ON, webhook de entrada e fila de envios. */
export function ConexaoEscrita({ conexaoId, pausada, aoMudar }: { conexaoId: number; pausada: boolean; aoMudar: () => void }) {
  const [escrita, setEscrita] = useState<Escrita | null>(null);
  const [funis, setFunis] = useState<Funil[] | null>(null);
  const [envios, setEnvios] = useState<Envio[]>([]);
  const [usuarios, setUsuarios] = useState<UsuarioResumo[]>([]);
  const [webhookUrl, setWebhookUrl] = useState<string | null>(null);
  const [mensagem, setMensagem] = useState<string | null>(null);
  const [ocupado, setOcupado] = useState(false);

  const carregar = useCallback(async () => {
    try {
      const [dados, fila] = await Promise.all([
        api.get<Escrita>(`/hub-integracoes/conexoes/${conexaoId}/escrita`),
        api.get<Envio[]>(`/hub-integracoes/envios?conexao_id=${conexaoId}`),
      ]);
      setEscrita(dados);
      setEnvios(fila);
    } catch (error) {
      setMensagem(erro(error, "Não foi possível carregar a configuração de escrita."));
    }
  }, [conexaoId]);

  useEffect(() => {
    carregar();
    api
      .get<UsuarioResumo[]>("/usuarios")
      .then(setUsuarios)
      .catch(() => setUsuarios([]));
  }, [carregar]);

  async function acao<T>(rotulo: string, chamada: () => Promise<T>, sucesso: (r: T) => string) {
    setOcupado(true);
    setMensagem(null);
    try {
      const resultado = await chamada();
      setMensagem(sucesso(resultado));
      await carregar();
    } catch (error) {
      setMensagem(erro(error, `Não foi possível ${rotulo}.`));
      await carregar(); // desfaz a mudança otimista com o que está gravado
    } finally {
      setOcupado(false);
    }
  }

  function salvar(mudancas: Partial<Escrita>) {
    setEscrita((atual) => (atual ? { ...atual, ...mudancas } : atual)); // otimista: a caixa responde na hora
    return acao(
      "salvar",
      () => api.put<Escrita>(`/hub-integracoes/conexoes/${conexaoId}/escrita`, mudancas),
      () => "Configuração salva.",
    );
  }

  if (!escrita) return <div className="mt-2 text-muted">{mensagem ?? "Carregando…"}</div>;
  const estagios = funis?.flatMap((f) => f.estagios.map((e) => ({ ...e, funil: f }))) ?? [];

  return (
    <div className="mt-2 flex flex-col gap-3 rounded-md bg-surf2 p-3" data-testid="conexao-escrita">
      {mensagem && <div className="text-muted" role="status">{mensagem}</div>}

      <div className="flex flex-col gap-1.5">
        <div className="font-semibold text-text">O que a B2B ON pode fazer neste CRM</div>
        <label className="flex items-start gap-2">
          <input
            type="checkbox"
            checked={escrita.deduplicar}
            disabled={ocupado}
            onChange={(e) => salvar({ deduplicar: e.target.checked })}
          />
          <span>
            <b>Não abordar quem o CRM já conhece</b> — antes de cada envio do PREDATOR, conferir se a empresa já é
            cliente, tem negócio aberto ou se o contato pediu opt-out (só leitura).
          </span>
        </label>
        <label className="flex items-start gap-2">
          <input
            type="checkbox"
            checked={escrita.predator}
            disabled={ocupado}
            onChange={(e) => salvar({ predator: e.target.checked })}
            data-testid="escrita-predator"
          />
          <span>
            <b>PREDATOR → CRM</b> — criar empresa e contato (sem alterar os que já existem), registrar as mensagens
            enviadas, criar o negócio quando a reunião é agendada e levar o opt-out.
          </span>
        </label>
        <label className="flex items-start gap-2">
          <input
            type="checkbox"
            checked={escrita.map}
            disabled={ocupado}
            onChange={(e) => salvar({ map: e.target.checked })}
            data-testid="escrita-map"
          />
          <span>
            <b>MAP → CRM</b> — gravar o score e o nível de risco de churn nas contas-cliente e criar uma tarefa para o
            dono quando a conta fica crítica (no máximo uma por mês).
          </span>
        </label>
      </div>

      {escrita.predator && (
        <div className="flex flex-col gap-1.5">
          <div className="font-semibold text-text">Onde criar o negócio</div>
          {funis === null ? (
            <Button
              size="sm"
              variant="ghost"
              className="self-start"
              disabled={ocupado || pausada}
              onClick={() =>
                acao(
                  "ler os funis",
                  async () => {
                    const lidos = await api.get<Funil[]>(`/hub-integracoes/conexoes/${conexaoId}/funis`);
                    setFunis(lidos);
                    return lidos;
                  },
                  (lidos) => `${lidos.length} funil(is) lido(s) do CRM.`,
                )
              }
            >
              Ler funis e estágios do CRM
            </Button>
          ) : (
            <Select
              aria-label="Estágio do negócio"
              value={escrita.estagio_id ?? ""}
              onChange={(e) => {
                const escolhido = estagios.find((s) => s.id === e.target.value);
                salvar({ estagio_id: e.target.value || null, pipeline_id: escolhido?.funil.id ?? null });
              }}
            >
              <option value="">Escolha o estágio inicial…</option>
              {estagios.map((s) => (
                <option key={`${s.funil.id}-${s.id}`} value={s.id}>
                  {s.funil.nome} → {s.nome}
                </option>
              ))}
            </Select>
          )}
          {escrita.estagio_id && <div className="text-muted">Estágio atual: {escrita.estagio_id}</div>}
          <Input
            type="number"
            min={1}
            max={730}
            label={
              escrita.sistema === "salesforce"
                ? "Previsão de fechamento: dias após a reunião (obrigatório no Salesforce)"
                : "Previsão de fechamento: dias após a reunião (opcional)"
            }
            defaultValue={escrita.prazo_fechamento_dias ?? ""}
            onBlur={(e) => {
              const valor = e.target.value ? Number(e.target.value) : null;
              if (valor !== escrita.prazo_fechamento_dias) salvar({ prazo_fechamento_dias: valor });
            }}
          />
          {usuarios.length > 0 && (
            <details>
              <summary className="cursor-pointer text-muted">Dono no CRM de cada vendedor (opcional)</summary>
              <div className="mt-1.5 flex flex-col gap-1.5">
                {usuarios.map((u) => (
                  <Input
                    key={u.id}
                    label={u.nome}
                    placeholder="Id do usuário/dono no CRM"
                    defaultValue={escrita.donos[String(u.id)] ?? ""}
                    onBlur={(e) => {
                      const valor = e.target.value.trim();
                      if (valor === (escrita.donos[String(u.id)] ?? "")) return;
                      const donos = { ...escrita.donos };
                      if (valor) donos[String(u.id)] = valor;
                      else delete donos[String(u.id)];
                      salvar({ donos });
                    }}
                  />
                ))}
              </div>
            </details>
          )}
        </div>
      )}

      {(escrita.predator || escrita.map) && (
        <div className="flex flex-col gap-1.5">
          <div className="font-semibold text-text">Campos da B2B ON no CRM</div>
          <div className="text-muted">
            A B2B ON só atualiza campos próprios — nunca os campos que o seu time edita.
            {CRIA_CAMPOS.has(escrita.sistema)
              ? " Clique para criar os campos automaticamente."
              : " Crie os campos no CRM e informe aqui o nome interno (ex.: B2BON_Score_Risco__c) ou o id do campo personalizado."}
          </div>
          {CRIA_CAMPOS.has(escrita.sistema) && (
            <Button
              size="sm"
              variant="ghost"
              className="self-start"
              disabled={ocupado || pausada}
              onClick={() =>
                acao(
                  "criar os campos",
                  () => api.post(`/hub-integracoes/conexoes/${conexaoId}/preparar-campos`),
                  () => "Campos criados no CRM.",
                )
              }
            >
              Criar campos no CRM
            </Button>
          )}
          {CAMPOS.map((campo) => (
            <Input
              key={campo.chave}
              label={campo.rotulo}
              defaultValue={escrita.campos[campo.chave] ?? ""}
              onBlur={(e) => {
                const valor = e.target.value.trim() || null;
                if (valor === (escrita.campos[campo.chave] ?? null)) return;
                salvar({ campos: { ...escrita.campos, [campo.chave]: valor } });
              }}
            />
          ))}
        </div>
      )}

      <div className="flex flex-wrap gap-1.5">
        {escrita.deduplicar && (
          <Button
            size="sm"
            variant="ghost"
            disabled={ocupado || pausada}
            onClick={() =>
              acao(
                "ler o CRM",
                () =>
                  api.post<{ registros: number; clientes: number; negocios_abertos: number; optouts: number }>(
                    `/hub-integracoes/conexoes/${conexaoId}/indice`,
                  ),
                (r) =>
                  `CRM lido: ${r.registros} registro(s), ${r.clientes} de clientes, ${r.negocios_abertos} com negócio aberto, ${r.optouts} opt-out(s).`,
              )
            }
          >
            Atualizar deduplicação agora
          </Button>
        )}
        {escrita.map && (
          <Button
            size="sm"
            variant="ghost"
            disabled={ocupado || pausada}
            onClick={() =>
              acao(
                "publicar os sinais",
                () => api.post<{ contas: number; enfileiradas: number }>(`/hub-integracoes/conexoes/${conexaoId}/sinais-map`),
                (r) => `${r.contas} conta(s)-cliente avaliada(s); ${r.enfileiradas} atualização(ões) na fila.`,
              )
            }
          >
            Publicar sinais do MAP agora
          </Button>
        )}
        <Button
          size="sm"
          variant="ghost"
          disabled={ocupado}
          onClick={() =>
            acao(
              "gerar a URL",
              async () => {
                const r = await api.post<{ url: string }>(`/hub-integracoes/conexoes/${conexaoId}/webhook-entrada`);
                setWebhookUrl(r.url);
                return r;
              },
              () => "URL gerada. Copie agora: ela não será mostrada de novo.",
            )
          }
        >
          {escrita.webhook_entrada_ativo ? "Gerar nova URL de webhook" : "Gerar URL de webhook"}
        </Button>
        <Button
          size="sm"
          variant="ghost"
          disabled={ocupado}
          onClick={() =>
            acao(
              pausada ? "retomar" : "pausar",
              async () => {
                const r = await api.put(`/hub-integracoes/conexoes/${conexaoId}/status`, {
                  status: pausada ? "ativa" : "pausada",
                });
                aoMudar();
                return r;
              },
              () => (pausada ? "Conexão retomada." : "Conexão pausada: nada é lido nem escrito até retomar."),
            )
          }
        >
          {pausada ? "Retomar conexão" : "Pausar conexão"}
        </Button>
      </div>
      {webhookUrl && (
        <div className="rounded-md border border-border bg-surf p-2">
          <div className="text-muted">
            Cadastre esta URL no CRM (webhook/automação ao alterar empresa, contato ou negócio):
          </div>
          <code className="break-all text-text" data-testid="webhook-url">
            {webhookUrl}
          </code>
        </div>
      )}

      <div className="flex flex-col gap-1">
        <div className="font-semibold text-text">Últimos envios ao CRM</div>
        {envios.length === 0 && <div className="text-muted">Nada enviado ainda.</div>}
        {envios.slice(0, 20).map((envio) => (
          <div key={envio.id} className="flex flex-wrap items-center gap-2 border-t border-border pt-1">
            <Badge tone={tomStatus(envio.status)}>{envio.status}</Badge>
            <span>{OPERACOES[envio.operacao] ?? envio.operacao}</span>
            <span className="text-muted">{envio.ultimo_erro ?? envio.resultado ?? ""}</span>
            {(envio.status === "desistido" || envio.status === "pulado") && (
              <Button
                size="sm"
                variant="ghost"
                disabled={ocupado}
                onClick={() =>
                  acao(
                    "reprocessar",
                    () => api.post(`/hub-integracoes/envios/${envio.id}/reprocessar`),
                    () => "Envio voltou para a fila.",
                  )
                }
              >
                Reprocessar
              </Button>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
