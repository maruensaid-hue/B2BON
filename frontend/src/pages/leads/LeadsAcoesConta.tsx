import { useEffect, useState, type FormEvent } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, SectionLabel } from "@/components/ui/Card";
import { Input, Select, Textarea } from "@/components/ui/Input";
import { Modal } from "@/components/ui/Modal";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";

interface LeadConta {
  id: number;
  nome: string;
  nome_fantasia: string | null;
  cnpj: string | null;
  dominio: string | null;
  segmento: string | null;
  porte: string | null;
  regiao: string | null;
  vendedor_usuario_id: number | null;
  proximo_passo: string | null;
  proximo_passo_em: string | null;
}

interface Decisor {
  id: number;
  nome: string;
  cargo: string | null;
  linkedin_url: string | null;
  email: string | null;
  telefone: string | null;
}

interface ContaResumo {
  id: number;
  nome: string;
  nome_fantasia: string | null;
}

interface EstagioFunil {
  id: number;
  nome: string;
  ordem: number;
  tipo: "aberto" | "ganho" | "perdido";
}

interface Negocio {
  id: number;
  estagio_id: number;
  nome: string;
  valor: number;
  probabilidade: number;
}

interface Reuniao {
  id: number;
  decisor_id: number;
  decisor_nome: string;
  data_hora: string;
  status: string;
  horarios_propostos: string[];
  horario_confirmado: string | null;
}

interface Cadencia {
  id: number;
  nome: string;
  status: string;
}

interface UsuarioResumo {
  id: number;
  nome: string;
}

function toneStatusReuniao(status: string): "cyan" | "green" | "amber" | "red" | "muted" {
  if (status === "agendada") return "cyan";
  if (status === "realizada") return "green";
  if (status === "horarios_propostos") return "amber";
  if (status === "no_show" || status === "cancelada") return "red";
  return "muted";
}

/** "Ações na conta" — detalhe de um lead (E-Leads): dados da empresa,
 * próximo passo, contatos, oportunidades, reuniões e cadência, tudo num
 * só lugar (modelo Pipedrive/HubSpot), reaproveitando os mesmos endpoints
 * já usados no Kanban/Reuniões/Cadências para conta vinda de ICP. */
export function LeadsAcoesConta() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { usuario } = useAuth();
  const isGestor = usuario?.papel === "admin" || usuario?.papel === "super_admin";
  const contaId = Number(id);

  const [conta, setConta] = useState<LeadConta | null>(null);
  const [decisores, setDecisores] = useState<Decisor[]>([]);
  const [estagios, setEstagios] = useState<EstagioFunil[]>([]);
  const [negocios, setNegocios] = useState<Negocio[]>([]);
  const [reunioes, setReunioes] = useState<Reuniao[]>([]);
  const [cadencias, setCadencias] = useState<Cadencia[]>([]);
  const [vendedores, setVendedores] = useState<UsuarioResumo[]>([]);
  const [todasAsContas, setTodasAsContas] = useState<ContaResumo[]>([]);

  const [editandoEmpresa, setEditandoEmpresa] = useState(false);
  const [editandoProximoPasso, setEditandoProximoPasso] = useState(false);
  const [decisorEmEdicaoId, setDecisorEmEdicaoId] = useState<number | null>(null);
  const [modalContato, setModalContato] = useState(false);
  const [modalNegocio, setModalNegocio] = useState(false);
  const [modalReuniao, setModalReuniao] = useState(false);
  const [cadenciaSelecionadaId, setCadenciaSelecionadaId] = useState<number | null>(null);
  const [gerandoCadencia, setGerandoCadencia] = useState(false);

  const [carregando, setCarregando] = useState<string | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [mensagem, setMensagem] = useState<string | null>(null);

  async function carregar() {
    try {
      const [contaResp, decisoresResp, estagiosResp, negociosResp, reunioesResp, cadenciasResp] = await Promise.all([
        api.get<LeadConta>(`/contas/${contaId}`),
        api.get<Decisor[]>(`/contas/${contaId}/decisores`),
        api.get<EstagioFunil[]>("/crm/estagios"),
        api.get<Negocio[]>(`/crm/negocios?conta_id=${contaId}`),
        api.get<Reuniao[]>(`/reunioes?conta_id=${contaId}`),
        api.get<Cadencia[]>("/cadencias"),
      ]);
      setConta(contaResp);
      setDecisores(decisoresResp);
      setEstagios(estagiosResp);
      setNegocios(negociosResp);
      setReunioes(reunioesResp);
      setCadencias(cadenciasResp);
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível carregar a conta.");
    }
  }

  useEffect(() => {
    carregar();
  }, [contaId]);

  useEffect(() => {
    api
      .get<ContaResumo[]>("/contas")
      .then(setTodasAsContas)
      .catch(() => undefined);
  }, []);

  useEffect(() => {
    if (isGestor) {
      api
        .get<UsuarioResumo[]>("/usuarios")
        .then(setVendedores)
        .catch(() => undefined);
    }
  }, [isGestor]);

  async function executar(nomeAcao: string, acao: () => Promise<void>) {
    setErro(null);
    setCarregando(nomeAcao);
    try {
      await acao();
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível concluir a ação.");
    } finally {
      setCarregando(null);
    }
  }

  async function salvarEmpresa(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    await executar("salvar-empresa", async () => {
      await api.put(`/contas/${contaId}`, {
        nome: String(form.get("nome")),
        cnpj: String(form.get("cnpj") || "") || null,
        nome_fantasia: String(form.get("nome_fantasia") || "") || null,
        dominio: String(form.get("dominio") || "") || null,
        segmento: String(form.get("segmento") || "") || null,
        porte: String(form.get("porte") || "") || null,
        regiao: String(form.get("regiao") || "") || null,
      });
      setEditandoEmpresa(false);
      await carregar();
    });
  }

  async function atribuirVendedor(vendedorUsuarioId: number | null) {
    await executar("atribuir-vendedor", async () => {
      await api.put(`/saude-contas/contas/${contaId}/vendedor`, { vendedor_usuario_id: vendedorUsuarioId });
      await carregar();
    });
  }

  async function salvarProximoPasso(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    await executar("proximo-passo", async () => {
      const dataHora = String(form.get("proximo_passo_em") || "");
      await api.put(`/contas/${contaId}/proximo-passo`, {
        proximo_passo: String(form.get("proximo_passo") || "") || null,
        proximo_passo_em: dataHora ? new Date(dataHora).toISOString() : null,
      });
      setEditandoProximoPasso(false);
      await carregar();
    });
  }

  async function criarContato(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    await executar("novo-contato", async () => {
      await api.post(`/contas/${contaId}/decisores`, {
        nome: String(form.get("nome")),
        cargo: String(form.get("cargo") || "") || null,
        email: String(form.get("email") || "") || null,
        telefone: String(form.get("telefone") || "") || null,
      });
      setModalContato(false);
      await carregar();
    });
  }

  async function salvarContato(decisorId: number, event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const novaContaId = Number(form.get("conta_id"));
    await executar(`salvar-contato-${decisorId}`, async () => {
      await api.put(`/contas/${contaId}/decisores/${decisorId}`, {
        nome: String(form.get("nome")),
        cargo: String(form.get("cargo") || "") || null,
        email: String(form.get("email") || "") || null,
        telefone: String(form.get("telefone") || "") || null,
        linkedin_url: String(form.get("linkedin_url") || "") || null,
        conta_id: novaContaId && novaContaId !== contaId ? novaContaId : null,
      });
      setDecisorEmEdicaoId(null);
      await carregar();
    });
  }

  async function criarNegocio(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    await executar("novo-negocio", async () => {
      await api.post("/crm/negocios", {
        conta_id: contaId,
        nome: String(form.get("nome")),
        valor: Number(form.get("valor") || 0),
      });
      setModalNegocio(false);
      await carregar();
    });
  }

  async function moverEstagio(negocioId: number, estagioId: number) {
    await executar(`mover-${negocioId}`, async () => {
      await api.put(`/crm/negocios/${negocioId}/estagio`, { estagio_id: estagioId });
      await carregar();
    });
  }

  async function agendarReuniao(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const decisorId = Number(form.get("decisor_id"));
    if (!decisorId) {
      setErro("Selecione um contato.");
      return;
    }
    await executar("agendar-reuniao", async () => {
      await api.post(`/decisores/${decisorId}/reunioes/propor`, {
        vendedor_id: String(usuario?.id ?? ""),
        duracao_minutos: 30,
      });
      setModalReuniao(false);
      await carregar();
    });
  }

  async function confirmarHorario(reuniaoId: number, horario: string) {
    await executar(`confirmar-${reuniaoId}`, async () => {
      await api.post(`/reunioes/${reuniaoId}/confirmar`, { horario_escolhido: horario });
      await carregar();
    });
  }

  async function gerarCadencia() {
    if (cadenciaSelecionadaId === null) {
      setErro("Selecione uma cadência.");
      return;
    }
    setGerandoCadencia(true);
    setErro(null);
    setMensagem(null);
    try {
      const resultado = await api.post<{ mensagens_geradas: number; contas_sem_decisor: number[] }>(
        `/cadencias/${cadenciaSelecionadaId}/gerar`,
        { conta_ids: [contaId] },
      );
      if (resultado.contas_sem_decisor.length > 0) {
        setErro("Esta conta ainda não tem um contato cadastrado — cadastre um contato antes de gerar a cadência.");
      } else {
        setMensagem(`${resultado.mensagens_geradas} mensagem(ns) gerada(s). Revise em Aprovações.`);
      }
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível gerar a cadência.");
    } finally {
      setGerandoCadencia(false);
    }
  }

  if (!conta) {
    return (
      <div className="p-5.5">
        {erro && <div className="mb-4 text-[12px] text-red">{erro}</div>}
        <div className="text-[12px] text-muted">Carregando...</div>
      </div>
    );
  }

  return (
    <div className="p-5.5">
      <button
        type="button"
        onClick={() => navigate("/leads/empresas")}
        className="mb-3 text-[11px] text-muted hover:text-cyan"
      >
        ← Voltar para Empresas
      </button>

      <div className="mb-5">
        <div className="font-head text-xl font-bold">{conta.nome_fantasia || conta.nome}</div>
        <div className="mt-0.5 text-[11px] text-muted">Lead avulso — fora do recorte de ICP</div>
      </div>

      {erro && <div className="mb-4 text-[12px] text-red">{erro}</div>}
      {mensagem && <div className="mb-4 text-[12px] text-green">{mensagem}</div>}

      <div className="mb-4 grid grid-cols-1 gap-3.5 lg:grid-cols-2">
        <Card>
          <SectionLabel>Empresa</SectionLabel>
          {editandoEmpresa ? (
            <form onSubmit={salvarEmpresa} className="flex flex-col gap-3">
              <Input name="nome" required defaultValue={conta.nome} placeholder="Razão social" />
              <Input name="nome_fantasia" defaultValue={conta.nome_fantasia ?? ""} placeholder="Nome fantasia" />
              <Input name="cnpj" defaultValue={conta.cnpj ?? ""} placeholder="CNPJ" />
              <Input name="dominio" defaultValue={conta.dominio ?? ""} placeholder="Domínio (site)" />
              <Input name="segmento" defaultValue={conta.segmento ?? ""} placeholder="Segmento" />
              <Input name="porte" defaultValue={conta.porte ?? ""} placeholder="Porte" />
              <Input name="regiao" defaultValue={conta.regiao ?? ""} placeholder="Região (UF)" />
              <div className="flex gap-2">
                <Button size="sm" type="submit" disabled={carregando !== null}>
                  {carregando === "salvar-empresa" ? "Salvando..." : "Salvar"}
                </Button>
                <Button size="sm" variant="ghost" type="button" onClick={() => setEditandoEmpresa(false)}>
                  Cancelar
                </Button>
              </div>
            </form>
          ) : (
            <div className="mb-2">
              <div className="mb-2 grid grid-cols-2 gap-2 text-[11px] text-muted">
                <div>Razão social: {conta.nome}</div>
                <div>CNPJ: {conta.cnpj ?? "—"}</div>
                <div>Domínio: {conta.dominio ?? "—"}</div>
                <div>Segmento: {conta.segmento ?? "—"}</div>
              </div>
              <Button size="sm" variant="ghost" onClick={() => setEditandoEmpresa(true)}>
                Editar empresa
              </Button>
            </div>
          )}

          <div className="mt-3">
            <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">Vendedor responsável</div>
            {isGestor ? (
              <Select
                value={conta.vendedor_usuario_id ?? ""}
                onChange={(event) => atribuirVendedor(event.target.value ? Number(event.target.value) : null)}
                disabled={carregando !== null}
              >
                <option value="">Sem vendedor atribuído</option>
                {vendedores.map((vendedor) => (
                  <option key={vendedor.id} value={vendedor.id}>
                    {vendedor.nome}
                  </option>
                ))}
              </Select>
            ) : (
              <div className="text-[11px] text-muted">
                {conta.vendedor_usuario_id === null
                  ? "Sem vendedor atribuído"
                  : conta.vendedor_usuario_id === usuario?.id
                    ? "Atribuído a você"
                    : "Atribuído a outro vendedor"}
              </div>
            )}
          </div>
        </Card>

        <Card>
          <SectionLabel>Próximo passo</SectionLabel>
          {editandoProximoPasso ? (
            <form onSubmit={salvarProximoPasso} className="flex flex-col gap-3">
              <Textarea name="proximo_passo" rows={2} defaultValue={conta.proximo_passo ?? ""} placeholder="Ex.: Ligar para apresentar proposta" />
              <Input
                name="proximo_passo_em"
                type="datetime-local"
                defaultValue={conta.proximo_passo_em ? conta.proximo_passo_em.slice(0, 16) : ""}
              />
              <div className="flex gap-2">
                <Button size="sm" type="submit" disabled={carregando !== null}>
                  {carregando === "proximo-passo" ? "Salvando..." : "Salvar"}
                </Button>
                <Button size="sm" variant="ghost" type="button" onClick={() => setEditandoProximoPasso(false)}>
                  Cancelar
                </Button>
              </div>
            </form>
          ) : (
            <div>
              {conta.proximo_passo ? (
                <div className="mb-2 text-[12px]">
                  <div className="text-text">{conta.proximo_passo}</div>
                  {conta.proximo_passo_em && (
                    <div className="mt-1 text-[11px] text-muted">
                      {new Date(conta.proximo_passo_em).toLocaleString("pt-BR")}
                    </div>
                  )}
                </div>
              ) : (
                <div className="mb-2 text-[12px] text-muted">Nenhum próximo passo definido.</div>
              )}
              <Button size="sm" variant="ghost" onClick={() => setEditandoProximoPasso(true)}>
                {conta.proximo_passo ? "Editar" : "Definir próximo passo"}
              </Button>
            </div>
          )}
        </Card>
      </div>

      <div className="mb-4 grid grid-cols-1 gap-3.5 lg:grid-cols-2">
        <Card>
          <div className="mb-2 flex items-center justify-between">
            <SectionLabel>Contatos</SectionLabel>
            <Button size="sm" variant="ghost" onClick={() => setModalContato(true)}>
              + Contato
            </Button>
          </div>
          <div className="flex flex-col gap-2 text-[12px]">
            {decisores.map((decisor) =>
              decisorEmEdicaoId === decisor.id ? (
                <form
                  key={decisor.id}
                  onSubmit={(event) => salvarContato(decisor.id, event)}
                  className="flex flex-col gap-2 rounded-lg border border-border p-2.5"
                >
                  <Input name="nome" required defaultValue={decisor.nome} placeholder="Nome" />
                  <Input name="cargo" defaultValue={decisor.cargo ?? ""} placeholder="Cargo" />
                  <Input name="email" type="email" defaultValue={decisor.email ?? ""} placeholder="E-mail" />
                  <Input name="telefone" defaultValue={decisor.telefone ?? ""} placeholder="Telefone" />
                  <Input name="linkedin_url" defaultValue={decisor.linkedin_url ?? ""} placeholder="LinkedIn (URL)" />
                  <div>
                    <div className="mb-1 text-[10px] tracking-wide text-muted uppercase">Empresa vinculada</div>
                    <Select name="conta_id" defaultValue={contaId}>
                      {todasAsContas.map((opcao) => (
                        <option key={opcao.id} value={opcao.id}>
                          {opcao.nome_fantasia || opcao.nome}
                        </option>
                      ))}
                    </Select>
                  </div>
                  <div className="flex gap-2">
                    <Button size="sm" type="submit" disabled={carregando !== null}>
                      {carregando === `salvar-contato-${decisor.id}` ? "Salvando..." : "Salvar"}
                    </Button>
                    <Button size="sm" variant="ghost" type="button" onClick={() => setDecisorEmEdicaoId(null)}>
                      Cancelar
                    </Button>
                  </div>
                </form>
              ) : (
                <div key={decisor.id} className="flex items-center justify-between border-b border-border py-1">
                  <div>
                    <span className="font-semibold text-text">{decisor.nome}</span>
                    {decisor.cargo && <span className="text-muted"> · {decisor.cargo}</span>}
                    {decisor.email && <span className="text-muted"> · {decisor.email}</span>}
                    {decisor.telefone && <span className="text-muted"> · {decisor.telefone}</span>}
                  </div>
                  <Button size="sm" variant="ghost" onClick={() => setDecisorEmEdicaoId(decisor.id)}>
                    Editar
                  </Button>
                </div>
              ),
            )}
            {decisores.length === 0 && <div className="text-muted">Nenhum contato cadastrado.</div>}
          </div>
        </Card>

        <Card>
          <div className="mb-2 flex items-center justify-between">
            <SectionLabel>Oportunidades</SectionLabel>
            <Button size="sm" variant="ghost" onClick={() => setModalNegocio(true)}>
              + Oportunidade
            </Button>
          </div>
          <div className="flex flex-col gap-2 text-[12px]">
            {negocios.map((negocio) => (
              <div key={negocio.id} className="rounded-lg border border-border p-2">
                <div className="mb-1 flex items-center justify-between">
                  <span className="font-semibold">{negocio.nome}</span>
                  <span className="font-head text-cyan">R${Math.round(negocio.valor / 1000)}k</span>
                </div>
                <Select
                  value={negocio.estagio_id}
                  onChange={(event) => moverEstagio(negocio.id, Number(event.target.value))}
                  disabled={carregando !== null}
                >
                  {estagios.map((estagio) => (
                    <option key={estagio.id} value={estagio.id}>
                      {estagio.nome}
                    </option>
                  ))}
                </Select>
              </div>
            ))}
            {negocios.length === 0 && <div className="text-muted">Nenhuma oportunidade ainda.</div>}
          </div>
        </Card>
      </div>

      <div className="grid grid-cols-1 gap-3.5 lg:grid-cols-2">
        <Card>
          <div className="mb-2 flex items-center justify-between">
            <SectionLabel>Reuniões</SectionLabel>
            <Button size="sm" variant="ghost" onClick={() => setModalReuniao(true)} disabled={decisores.length === 0}>
              + Agendar
            </Button>
          </div>
          <div className="flex flex-col gap-2 text-[12px]">
            {reunioes.map((reuniao) => (
              <div key={reuniao.id} className="rounded-lg border border-border p-2">
                <div className="mb-1 flex items-center justify-between">
                  <span className="font-semibold">{reuniao.decisor_nome}</span>
                  <Badge tone={toneStatusReuniao(reuniao.status)}>{reuniao.status}</Badge>
                </div>
                {reuniao.status === "horarios_propostos" && (
                  <div className="flex flex-wrap gap-1.5">
                    {reuniao.horarios_propostos.map((horario) => (
                      <Button key={horario} size="sm" onClick={() => confirmarHorario(reuniao.id, horario)}>
                        {new Date(horario).toLocaleString("pt-BR")}
                      </Button>
                    ))}
                  </div>
                )}
                {reuniao.status === "agendada" && (
                  <div className="text-[11px] text-muted">
                    {new Date(reuniao.horario_confirmado ?? reuniao.data_hora).toLocaleString("pt-BR")}
                  </div>
                )}
              </div>
            ))}
            {reunioes.length === 0 && <div className="text-muted">Nenhuma reunião agendada.</div>}
          </div>
        </Card>

        <Card>
          <SectionLabel>Cadência</SectionLabel>
          <div className="flex flex-col gap-2">
            <Select
              value={cadenciaSelecionadaId ?? ""}
              onChange={(event) => setCadenciaSelecionadaId(event.target.value ? Number(event.target.value) : null)}
            >
              <option value="">Selecione uma cadência</option>
              {cadencias.map((cadencia) => (
                <option key={cadencia.id} value={cadencia.id}>
                  {cadencia.nome} ({cadencia.status})
                </option>
              ))}
            </Select>
            <Button
              size="sm"
              disabled={gerandoCadencia || decisores.length === 0}
              onClick={gerarCadencia}
            >
              {gerandoCadencia ? "Gerando..." : "Gerar mensagens para este cliente"}
            </Button>
            {decisores.length === 0 && (
              <div className="text-[11px] text-muted">Cadastre um contato antes de gerar a cadência.</div>
            )}
          </div>
        </Card>
      </div>

      <Modal title="Novo contato" open={modalContato} onClose={() => setModalContato(false)}>
        <form onSubmit={criarContato} className="flex flex-col gap-3">
          <Input name="nome" required placeholder="Nome completo" />
          <Input name="cargo" placeholder="Cargo" />
          <Input name="email" type="email" placeholder="E-mail" />
          <Input name="telefone" placeholder="Telefone" />
          <Button type="submit" disabled={carregando !== null} className="w-full justify-center">
            {carregando === "novo-contato" ? "Cadastrando..." : "Cadastrar contato"}
          </Button>
        </form>
      </Modal>

      <Modal title="Nova oportunidade" open={modalNegocio} onClose={() => setModalNegocio(false)}>
        <form onSubmit={criarNegocio} className="flex flex-col gap-3">
          <Input name="nome" required placeholder="Ex.: Licença Professional — 12 meses" />
          <Input name="valor" type="number" step="0.01" placeholder="Valor (R$)" />
          <Button type="submit" disabled={carregando !== null} className="w-full justify-center">
            {carregando === "novo-negocio" ? "Criando..." : "Criar oportunidade"}
          </Button>
        </form>
      </Modal>

      <Modal title="Agendar reunião" open={modalReuniao} onClose={() => setModalReuniao(false)}>
        <form onSubmit={agendarReuniao} className="flex flex-col gap-3">
          <div>
            <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">Contato</div>
            <Select name="decisor_id" required defaultValue="">
              <option value="" disabled>
                Selecione o contato
              </option>
              {decisores.map((decisor) => (
                <option key={decisor.id} value={decisor.id}>
                  {decisor.nome}
                </option>
              ))}
            </Select>
          </div>
          <Button type="submit" disabled={carregando !== null} className="w-full justify-center">
            {carregando === "agendar-reuniao" ? "Propondo horários..." : "Propor horários"}
          </Button>
        </form>
      </Modal>
    </div>
  );
}
