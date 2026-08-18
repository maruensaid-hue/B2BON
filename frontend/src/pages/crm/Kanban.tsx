import { useEffect, useMemo, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";

import { ListaAtividades, type Atividade } from "@/components/ListaAtividades";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Input, Select, Textarea } from "@/components/ui/Input";
import { Modal } from "@/components/ui/Modal";
import { SeletorArquivo } from "@/components/ui/SeletorArquivo";
import { ContaDetalheModal } from "@/pages/prospeccao/ContaDetalheModal";
import { api, ApiError, getBlob, postFile } from "@/lib/api";

const MOTIVOS_PERDA = [
  "Preço/orçamento",
  "Escolheu concorrente",
  "Não é fit com o produto",
  "Perdeu contato/sem resposta",
  "Projeto cancelado",
  "Outro",
];

interface EstagioFunil {
  id: number;
  nome: string;
  ordem: number;
  tipo: "aberto" | "ganho" | "perdido";
}

interface Negocio {
  id: number;
  conta_id: number;
  conta_nome: string;
  decisor_id: number | null;
  decisor_nome: string | null;
  estagio_id: number;
  nome: string;
  valor: number;
  probabilidade: number;
}

interface DecisorResumo {
  id: number;
  nome: string;
}

interface PropostaNegocio {
  id: number;
  negocio_id: number;
  versao: number;
  nome_arquivo: string;
  tipo_mime: string;
  tamanho_bytes: number;
  gerada_automaticamente: boolean;
  enviada_por_usuario_id: number | null;
  criado_em: string;
}

interface ICP {
  id: number;
  nome: string;
  ativo: boolean;
}

interface Conta {
  id: number;
  nome: string;
  nome_fantasia: string | null;
  icp_id: number | null;
}

export function Kanban() {
  const [estagios, setEstagios] = useState<EstagioFunil[]>([]);
  const [negocios, setNegocios] = useState<Negocio[]>([]);
  const [icps, setIcps] = useState<ICP[]>([]);
  const [erro, setErro] = useState<string | null>(null);
  const [modalAberto, setModalAberto] = useState(false);
  const [contaOrigem, setContaOrigem] = useState<"existente" | "nova">("existente");
  const [semIcp, setSemIcp] = useState(false);
  const [icpSelecionadoId, setIcpSelecionadoId] = useState<number | null>(null);
  const [todasAsContas, setTodasAsContas] = useState<Conta[]>([]);
  const [buscaContaExistente, setBuscaContaExistente] = useState("");
  const [contaExistenteSelecionadaId, setContaExistenteSelecionadaId] = useState<number | null>(null);
  const [sugestoesContaAbertas, setSugestoesContaAbertas] = useState(false);
  const [negocioArrastadoId, setNegocioArrastadoId] = useState<number | null>(null);
  const [salvandoNegocio, setSalvandoNegocio] = useState(false);
  const [negocioEmEdicao, setNegocioEmEdicao] = useState<Negocio | null>(null);
  const [salvandoEdicao, setSalvandoEdicao] = useState(false);
  const [negocioParaExcluir, setNegocioParaExcluir] = useState<number | null>(null);
  const [negocioParaMarcarPerdido, setNegocioParaMarcarPerdido] = useState<{ negocio: Negocio; estagioId: number } | null>(null);
  const [motivoPerdaSelecionado, setMotivoPerdaSelecionado] = useState(MOTIVOS_PERDA[0]);
  const [motivoPerdaOutro, setMotivoPerdaOutro] = useState("");
  const [salvandoMotivoPerda, setSalvandoMotivoPerda] = useState(false);
  const [decisoresDaContaSelecionada, setDecisoresDaContaSelecionada] = useState<DecisorResumo[]>([]);
  const [decisoresDaContaEmEdicao, setDecisoresDaContaEmEdicao] = useState<DecisorResumo[]>([]);
  const [atividadesDoNegocio, setAtividadesDoNegocio] = useState<Atividade[]>([]);
  const [propostasDoNegocio, setPropostasDoNegocio] = useState<PropostaNegocio[]>([]);
  const [enviandoProposta, setEnviandoProposta] = useState(false);
  const [erroProposta, setErroProposta] = useState<string | null>(null);
  const [contaEmEdicaoModalAberta, setContaEmEdicaoModalAberta] = useState(false);

  // Defesa contra a duplicidade de estágios já corrigida no backend
  // (UniqueConstraint tenant_id+ordem) — se ainda houver dado antigo
  // duplicado, a tela não volta a mostrar a mesma fila duas vezes.
  const estagiosUnicos = useMemo(() => {
    const vistos = new Set<string>();
    return estagios
      .filter((estagio) => {
        const chave = `${estagio.nome}::${estagio.tipo}`;
        if (vistos.has(chave)) return false;
        vistos.add(chave);
        return true;
      })
      .sort((a, b) => a.ordem - b.ordem);
  }, [estagios]);

  async function carregar() {
    try {
      const [estagiosResp, negociosResp] = await Promise.all([
        api.get<EstagioFunil[]>("/crm/estagios"),
        api.get<Negocio[]>("/crm/negocios"),
      ]);
      setEstagios(estagiosResp);
      setNegocios(negociosResp);
    } catch {
      setErro("Não foi possível carregar o kanban.");
    }
  }

  useEffect(() => {
    carregar();
    api
      .get<ICP[]>("/icp")
      .then(setIcps)
      .catch(() => undefined);
    api
      .get<Conta[]>("/contas")
      .then(setTodasAsContas)
      .catch(() => setErro("Não foi possível carregar as contas existentes."));
  }, []);

  // Filtro opcional por ICP na hora de escolher "conta existente" — sem
  // ICP selecionado, mostra todas (inclusive leads sem ICP, que antes
  // ficavam impossíveis de escolher aqui).
  const contasParaSelecionar = useMemo(() => {
    if (icpSelecionadoId === null) return todasAsContas;
    return todasAsContas.filter((conta) => conta.icp_id === icpSelecionadoId);
  }, [todasAsContas, icpSelecionadoId]);

  // Busca com autocompletar — com muitas contas vinculadas a uma empresa
  // ou vendedor, rolar uma lista inteira num <select> nativo fica
  // inviável; digitar o nome e escolher entre os resultados é bem mais
  // rápido (limita a 20 sugestões por vez, só por legibilidade).
  const sugestoesContaExistente = useMemo(() => {
    const termo = buscaContaExistente.trim().toLowerCase();
    const lista = termo
      ? contasParaSelecionar.filter((conta) => (conta.nome_fantasia || conta.nome).toLowerCase().includes(termo))
      : contasParaSelecionar;
    return lista.slice(0, 20);
  }, [contasParaSelecionar, buscaContaExistente]);

  // O negócio precisa de um contato responsável — busca os decisores da
  // conta escolhida assim que ela é selecionada, pra popular o <Select>.
  useEffect(() => {
    if (contaExistenteSelecionadaId === null) {
      setDecisoresDaContaSelecionada([]);
      return;
    }
    api
      .get<DecisorResumo[]>(`/contas/${contaExistenteSelecionadaId}/decisores`)
      .then(setDecisoresDaContaSelecionada)
      .catch(() => setDecisoresDaContaSelecionada([]));
  }, [contaExistenteSelecionadaId]);

  function recarregarDecisoresDaContaEmEdicao() {
    if (!negocioEmEdicao) return;
    api
      .get<DecisorResumo[]>(`/contas/${negocioEmEdicao.conta_id}/decisores`)
      .then(setDecisoresDaContaEmEdicao)
      .catch(() => setDecisoresDaContaEmEdicao([]));
  }

  useEffect(() => {
    if (!negocioEmEdicao) {
      setDecisoresDaContaEmEdicao([]);
      setAtividadesDoNegocio([]);
      setPropostasDoNegocio([]);
      return;
    }
    recarregarDecisoresDaContaEmEdicao();
    carregarAtividadesDoNegocio(negocioEmEdicao.id);
    carregarPropostasDoNegocio(negocioEmEdicao.id);
  }, [negocioEmEdicao]);

  async function carregarAtividadesDoNegocio(negocioId: number) {
    try {
      setAtividadesDoNegocio(await api.get<Atividade[]>(`/crm/negocios/${negocioId}/atividades`));
    } catch {
      setAtividadesDoNegocio([]);
    }
  }

  async function registrarAtividadeDoNegocio(tipo: string, descricao: string) {
    if (!negocioEmEdicao) return;
    await api.post(`/crm/negocios/${negocioEmEdicao.id}/atividades`, { tipo, descricao });
    await carregarAtividadesDoNegocio(negocioEmEdicao.id);
  }

  async function carregarPropostasDoNegocio(negocioId: number) {
    try {
      setPropostasDoNegocio(await api.get<PropostaNegocio[]>(`/crm/negocios/${negocioId}/propostas`));
    } catch {
      setPropostasDoNegocio([]);
    }
  }

  async function enviarProposta(arquivo: File) {
    if (!negocioEmEdicao || enviandoProposta) return;
    setEnviandoProposta(true);
    setErroProposta(null);
    try {
      await postFile(`/crm/negocios/${negocioEmEdicao.id}/propostas`, arquivo);
      await carregarPropostasDoNegocio(negocioEmEdicao.id);
    } catch (error) {
      setErroProposta(error instanceof ApiError ? error.message : "Não foi possível enviar a proposta.");
    } finally {
      setEnviandoProposta(false);
    }
  }

  async function baixarProposta(proposta: PropostaNegocio) {
    if (!negocioEmEdicao) return;
    try {
      const blob = await getBlob(`/crm/negocios/${negocioEmEdicao.id}/propostas/${proposta.id}/download`);
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = proposta.nome_arquivo;
      link.click();
      URL.revokeObjectURL(url);
    } catch {
      setErroProposta("Não foi possível baixar a proposta.");
    }
  }

  async function moverEstagio(negocioId: number, estagioId: number, motivoPerda?: string) {
    try {
      await api.put(`/crm/negocios/${negocioId}/estagio`, { estagio_id: estagioId, motivo_perda: motivoPerda });
      await carregar();
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível mover o negócio.");
    }
  }

  function tentarMoverEstagio(negocio: Negocio, estagioId: number) {
    if (negocio.estagio_id === estagioId) return;
    const estagioDestino = estagiosUnicos.find((e) => e.id === estagioId);
    if (estagioDestino?.tipo === "perdido") {
      setMotivoPerdaSelecionado(MOTIVOS_PERDA[0]);
      setMotivoPerdaOutro("");
      setNegocioParaMarcarPerdido({ negocio, estagioId });
      return;
    }
    moverEstagio(negocio.id, estagioId);
  }

  async function confirmarMotivoPerda() {
    if (!negocioParaMarcarPerdido || salvandoMotivoPerda) return;
    const motivo = motivoPerdaSelecionado === "Outro" ? motivoPerdaOutro.trim() : motivoPerdaSelecionado;
    if (!motivo) {
      setErro("Informe o motivo da perda.");
      return;
    }
    setSalvandoMotivoPerda(true);
    setErro(null);
    try {
      await moverEstagio(negocioParaMarcarPerdido.negocio.id, negocioParaMarcarPerdido.estagioId, motivo);
      setNegocioParaMarcarPerdido(null);
    } finally {
      setSalvandoMotivoPerda(false);
    }
  }

  async function excluirNegocio(negocioId: number) {
    try {
      await api.delete(`/crm/negocios/${negocioId}`);
      setNegocioParaExcluir(null);
      await carregar();
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível excluir o negócio.");
    }
  }

  function aoSoltarNoEstagio(estagioId: number) {
    if (negocioArrastadoId === null) return;
    const negocio = negocios.find((n) => n.id === negocioArrastadoId);
    setNegocioArrastadoId(null);
    if (!negocio || negocio.estagio_id === estagioId) return;
    tentarMoverEstagio(negocio, estagioId);
  }

  async function criarNegocio(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (salvandoNegocio) return;
    const form = new FormData(event.currentTarget);
    const nomeNegocio = String(form.get("nome"));
    const valor = Number(form.get("valor") || 0);

    setSalvandoNegocio(true);
    setErro(null);
    try {
      let contaId: number;
      let decisorId: number;
      if (contaOrigem === "existente") {
        contaId = Number(form.get("conta_id"));
        if (!contaId) {
          setErro("Selecione uma conta.");
          return;
        }
        decisorId = Number(form.get("decisor_id"));
        if (!decisorId) {
          setErro("Selecione o contato responsável pela oportunidade.");
          return;
        }
      } else {
        const nomeConta = String(form.get("nome_conta") || "").trim();
        if (!nomeConta) {
          setErro("Informe o nome do cliente.");
          return;
        }
        const nomeContato = String(form.get("nome_contato") || "").trim();
        if (!nomeContato) {
          setErro("Informe o contato responsável pela oportunidade.");
          return;
        }
        let contaCriada: Conta;
        if (semIcp) {
          contaCriada = await api.post<Conta>("/leads/contas", {
            nome: nomeConta,
            dominio: String(form.get("dominio_conta") || "") || null,
          });
        } else {
          if (icpSelecionadoId === null) {
            setErro("Selecione um ICP para cadastrar a conta nova (ou marque \"Sem ICP\").");
            return;
          }
          contaCriada = await api.post<Conta>(`/icp/${icpSelecionadoId}/contas`, {
            nome: nomeConta,
            dominio: String(form.get("dominio_conta") || "") || null,
          });
        }
        contaId = contaCriada.id;

        const decisorCriado = await api.post<DecisorResumo>(`/contas/${contaId}/decisores`, {
          nome: nomeContato,
          email: String(form.get("email_contato") || "") || null,
          telefone: String(form.get("telefone_contato") || "") || null,
        });
        decisorId = decisorCriado.id;
      }

      await api.post("/crm/negocios", { conta_id: contaId, decisor_id: decisorId, nome: nomeNegocio, valor });
      setModalAberto(false);
      setContaOrigem("existente");
      setSemIcp(false);
      setIcpSelecionadoId(null);
      setBuscaContaExistente("");
      setContaExistenteSelecionadaId(null);
      await carregar();
      if (contaOrigem === "nova") {
        api
          .get<Conta[]>("/contas")
          .then(setTodasAsContas)
          .catch(() => undefined);
      }
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível criar o negócio.");
    } finally {
      setSalvandoNegocio(false);
    }
  }

  async function salvarEdicaoNegocio(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!negocioEmEdicao || salvandoEdicao) return;
    const form = new FormData(event.currentTarget);
    setSalvandoEdicao(true);
    setErro(null);
    try {
      const decisorId = Number(form.get("decisor_id"));
      if (!decisorId) {
        setErro("Selecione o contato responsável pela oportunidade.");
        return;
      }
      await api.put(`/crm/negocios/${negocioEmEdicao.id}`, {
        nome: String(form.get("nome")),
        valor: Number(form.get("valor") || 0),
        probabilidade: Number(form.get("probabilidade") || 50),
        decisor_id: decisorId,
      });
      setNegocioEmEdicao(null);
      await carregar();
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível salvar as alterações do negócio.");
    } finally {
      setSalvandoEdicao(false);
    }
  }

  const valorTotal = negocios.reduce((soma, negocio) => soma + negocio.valor, 0);

  return (
    <div className="p-5.5">
      <div className="mb-5 flex items-end justify-between">
        <div>
          <div className="font-head text-xl font-bold">CRM — Pipeline</div>
          <div className="mt-0.5 text-[11px] text-muted">
            {negocios.length} negócio(s) · R${Math.round(valorTotal / 1000)}k em pipeline
          </div>
        </div>
        <Button size="sm" onClick={() => setModalAberto(true)}>
          + Novo negócio
        </Button>
      </div>

      {erro && <div className="mb-4 text-[12px] text-red">{erro}</div>}

      <div className="grid grid-cols-1 gap-2.5 overflow-x-auto sm:grid-cols-2 lg:grid-cols-4">
        {estagiosUnicos.map((estagio) => {
          const negociosDoEstagio = negocios.filter((negocio) => negocio.estagio_id === estagio.id);
          return (
            <div
              key={estagio.id}
              className="min-w-0"
              onDragOver={(event) => event.preventDefault()}
              onDrop={(event) => {
                event.preventDefault();
                aoSoltarNoEstagio(estagio.id);
              }}
            >
              <div className="mb-2 flex items-center gap-1.5 text-[10px] font-bold tracking-wide text-muted uppercase">
                {estagio.nome}
                <span className="rounded-full bg-cyan/15 px-1.5 py-px text-cyan">{negociosDoEstagio.length}</span>
              </div>
              {negociosDoEstagio.map((negocio) => (
                <Card
                  key={negocio.id}
                  className="mb-2 cursor-grab p-3 active:cursor-grabbing"
                  draggable
                  onDragStart={() => setNegocioArrastadoId(negocio.id)}
                  onDragEnd={() => setNegocioArrastadoId(null)}
                >
                  <div className="mb-1 flex items-start justify-between gap-2">
                    <div>
                      <div className="text-[10px] font-bold tracking-wide text-cyan uppercase">{negocio.conta_nome}</div>
                      <div className="text-[12px] font-bold">{negocio.nome}</div>
                      {negocio.decisor_nome && <div className="text-[10px] text-muted">{negocio.decisor_nome}</div>}
                    </div>
                    {negocioParaExcluir === negocio.id ? (
                      <div className="flex flex-shrink-0 items-center gap-1 text-[10px]">
                        <span className="text-muted">Excluir?</span>
                        <button type="button" className="text-red hover:underline" onClick={() => excluirNegocio(negocio.id)}>
                          Sim
                        </button>
                        <button type="button" className="text-muted hover:underline" onClick={() => setNegocioParaExcluir(null)}>
                          Não
                        </button>
                      </div>
                    ) : (
                      <div className="flex flex-shrink-0 items-center gap-1.5">
                        <button
                          type="button"
                          className="text-[11px] text-muted hover:text-cyan"
                          onClick={() => setNegocioEmEdicao(negocio)}
                          title="Editar negócio"
                        >
                          ✎
                        </button>
                        <button
                          type="button"
                          className="text-[11px] text-muted hover:text-red"
                          onClick={() => setNegocioParaExcluir(negocio.id)}
                          title="Excluir negócio"
                        >
                          🗑
                        </button>
                      </div>
                    )}
                  </div>
                  <div className="font-head mb-2 text-base font-bold text-cyan">
                    R${Math.round(negocio.valor / 1000)}k
                  </div>
                  <Select
                    value={negocio.estagio_id}
                    onChange={(event) => tentarMoverEstagio(negocio, Number(event.target.value))}
                  >
                    {estagiosUnicos.map((opcao) => (
                      <option key={opcao.id} value={opcao.id}>
                        {opcao.nome}
                      </option>
                    ))}
                  </Select>
                </Card>
              ))}
              {negociosDoEstagio.length === 0 && (
                <div className="rounded-xl border border-dashed border-border p-4 text-center text-[11px] text-muted">
                  Vazio
                </div>
              )}
            </div>
          );
        })}
      </div>

      <Modal title="Novo negócio" open={modalAberto} onClose={() => setModalAberto(false)}>
        <form onSubmit={criarNegocio} className="flex flex-col gap-3">
          <div>
            <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">Cliente</div>
            <div className="mb-2 flex gap-2">
              <button
                type="button"
                onClick={() => setContaOrigem("existente")}
                className={`flex-1 rounded-lg border px-3 py-1.5 text-[12px] ${
                  contaOrigem === "existente" ? "border-cyan bg-cyan/15 text-cyan" : "border-border text-muted"
                }`}
              >
                Conta existente
              </button>
              <button
                type="button"
                onClick={() => setContaOrigem("nova")}
                className={`flex-1 rounded-lg border px-3 py-1.5 text-[12px] ${
                  contaOrigem === "nova" ? "border-cyan bg-cyan/15 text-cyan" : "border-border text-muted"
                }`}
              >
                Cadastrar cliente novo
              </button>
            </div>

            {contaOrigem === "nova" && (
              <label className="mb-2 flex items-center gap-1.5 text-[11px] text-muted">
                <input
                  type="checkbox"
                  checked={semIcp}
                  onChange={(event) => {
                    setSemIcp(event.target.checked);
                    setIcpSelecionadoId(null);
                  }}
                />
                Sem ICP (lead avulso — indicação, evento, contato pessoal)
              </label>
            )}

            {!(contaOrigem === "nova" && semIcp) && (
              <Select
                value={icpSelecionadoId ?? ""}
                onChange={(event) => setIcpSelecionadoId(event.target.value ? Number(event.target.value) : null)}
                className="mb-2"
              >
                <option value="">{contaOrigem === "existente" ? "Filtrar por ICP" : "Selecione o ICP da conta"}</option>
                {icps.map((icp) => (
                  <option key={icp.id} value={icp.id}>
                    {icp.nome}
                  </option>
                ))}
              </Select>
            )}

            {contaOrigem === "existente" ? (
              <div className="relative">
                <Input
                  value={buscaContaExistente}
                  onChange={(event) => {
                    setBuscaContaExistente(event.target.value);
                    setContaExistenteSelecionadaId(null);
                    setSugestoesContaAbertas(true);
                  }}
                  onFocus={() => setSugestoesContaAbertas(true)}
                  onBlur={() => setTimeout(() => setSugestoesContaAbertas(false), 150)}
                  autoComplete="off"
                  placeholder={
                    contasParaSelecionar.length === 0 ? "Nenhuma conta cadastrada ainda" : "Digite o nome da empresa..."
                  }
                />
                <input type="hidden" name="conta_id" value={contaExistenteSelecionadaId ?? ""} />
                {sugestoesContaAbertas && sugestoesContaExistente.length > 0 && (
                  <div className="absolute z-10 mt-1 max-h-56 w-full overflow-y-auto rounded-lg border border-border bg-surf shadow-lg">
                    {sugestoesContaExistente.map((conta) => (
                      <button
                        key={conta.id}
                        type="button"
                        onMouseDown={(event) => event.preventDefault()}
                        onClick={() => {
                          setContaExistenteSelecionadaId(conta.id);
                          setBuscaContaExistente(conta.nome_fantasia || conta.nome);
                          setSugestoesContaAbertas(false);
                        }}
                        className="block w-full px-3 py-2 text-left text-[12px] hover:bg-surf2"
                      >
                        {conta.nome_fantasia || conta.nome}
                      </button>
                    ))}
                  </div>
                )}
                {sugestoesContaAbertas && buscaContaExistente && sugestoesContaExistente.length === 0 && (
                  <div className="absolute z-10 mt-1 w-full rounded-lg border border-border bg-surf p-2 text-[12px] text-muted shadow-lg">
                    Nenhuma conta encontrada com esse nome.
                  </div>
                )}
                {contaExistenteSelecionadaId !== null && (
                  <div className="mt-2">
                    <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">Contato responsável</div>
                    {decisoresDaContaSelecionada.length === 0 ? (
                      <div className="text-[11px] text-muted">
                        Esta conta ainda não tem contato cadastrado — cadastre um antes de criar a oportunidade.
                      </div>
                    ) : (
                      <Select name="decisor_id" required defaultValue="">
                        <option value="" disabled>
                          Selecione o contato
                        </option>
                        {decisoresDaContaSelecionada.map((decisor) => (
                          <option key={decisor.id} value={decisor.id}>
                            {decisor.nome}
                          </option>
                        ))}
                      </Select>
                    )}
                  </div>
                )}
              </div>
            ) : (
              <div className="flex flex-col gap-2">
                <Input name="nome_conta" required placeholder="Nome do cliente" />
                <Input name="dominio_conta" placeholder="Domínio (opcional)" />
                <div className="mt-1 text-[10px] tracking-wide text-muted uppercase">Contato responsável</div>
                <Input name="nome_contato" required placeholder="Nome do contato" />
                <Input name="email_contato" type="email" placeholder="E-mail do contato" />
                <Input name="telefone_contato" placeholder="Telefone do contato" />
              </div>
            )}
          </div>

          <div>
            <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">Nome do negócio</div>
            <Input name="nome" required placeholder="Ex: Licença Professional — 12 meses" />
          </div>
          <div>
            <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">Valor (R$)</div>
            <Input name="valor" type="number" step="0.01" placeholder="0,00" />
          </div>
          <Button type="submit" disabled={salvandoNegocio} className="mt-1 w-full justify-center">
            {salvandoNegocio ? "Criando..." : "Criar negócio"}
          </Button>
        </form>
      </Modal>

      <Modal title="Detalhes do negócio" open={negocioEmEdicao !== null} onClose={() => setNegocioEmEdicao(null)}>
        {negocioEmEdicao && (
          <div className="flex flex-col gap-4">
          <form onSubmit={salvarEdicaoNegocio} className="flex flex-col gap-3">
            <div className="flex items-center justify-between text-[11px] text-muted">
              <span>
                Empresa: <span className="font-semibold text-text">{negocioEmEdicao.conta_nome}</span>
              </span>
              <button
                type="button"
                className="text-cyan hover:underline"
                onClick={() => setContaEmEdicaoModalAberta(true)}
              >
                Editar empresa / enriquecer contatos
              </button>
            </div>
            <div>
              <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">Nome do negócio</div>
              <Input name="nome" required defaultValue={negocioEmEdicao.nome} />
            </div>
            <div>
              <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">Valor (R$)</div>
              <Input name="valor" type="number" step="0.01" defaultValue={negocioEmEdicao.valor} />
            </div>
            <div>
              <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">Probabilidade (%)</div>
              <Input
                name="probabilidade"
                type="number"
                min={0}
                max={100}
                defaultValue={negocioEmEdicao.probabilidade}
              />
            </div>
            <div>
              <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">Contato responsável</div>
              <Select name="decisor_id" required defaultValue={negocioEmEdicao.decisor_id ?? ""}>
                <option value="" disabled>
                  Selecione o contato
                </option>
                {decisoresDaContaEmEdicao.map((decisor) => (
                  <option key={decisor.id} value={decisor.id}>
                    {decisor.nome}
                  </option>
                ))}
              </Select>
            </div>
            <Button type="submit" disabled={salvandoEdicao} className="w-full justify-center">
              {salvandoEdicao ? "Salvando..." : "Salvar alterações"}
            </Button>
          </form>

          <ListaAtividades atividades={atividadesDoNegocio} aoRegistrar={registrarAtividadeDoNegocio} />

          <div>
            <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">Propostas</div>
            <div className="mb-3 flex flex-col gap-2 rounded-lg border border-border p-2.5">
              {erroProposta && <div className="text-[11px] text-red">{erroProposta}</div>}
              <SeletorArquivo
                accept=".pdf,.docx"
                disabled={enviandoProposta}
                onSelecionar={enviarProposta}
                rotulo={enviandoProposta ? "Enviando..." : "Selecionar arquivo"}
              />
              <Link
                to={`/crm/propostas/nova?negocio_id=${negocioEmEdicao.id}`}
                className="text-[11px] text-cyan hover:underline"
              >
                Gerar proposta automática →
              </Link>
            </div>

            {propostasDoNegocio.length === 0 ? (
              <div className="text-[11px] text-muted">Nenhuma proposta anexada ainda.</div>
            ) : (
              <div className="flex flex-col gap-1.5">
                {propostasDoNegocio.map((proposta) => (
                  <div key={proposta.id} className="flex items-center justify-between gap-2 border-b border-border py-1 text-[11px]">
                    <div>
                      <div className="text-text">
                        v{proposta.versao} — {proposta.nome_arquivo}
                        {proposta.gerada_automaticamente && (
                          <span className="ml-1.5 rounded-full bg-cyan/15 px-1.5 py-px text-[10px] text-cyan">
                            gerada automaticamente
                          </span>
                        )}
                      </div>
                      <div className="text-muted">{new Date(proposta.criado_em).toLocaleString("pt-BR")}</div>
                    </div>
                    <button type="button" className="text-cyan hover:underline" onClick={() => baixarProposta(proposta)}>
                      Baixar
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
          </div>
        )}
      </Modal>

      {contaEmEdicaoModalAberta && negocioEmEdicao && (
        <ContaDetalheModal
          contaId={negocioEmEdicao.conta_id}
          onClose={() => setContaEmEdicaoModalAberta(false)}
          onAtualizado={recarregarDecisoresDaContaEmEdicao}
        />
      )}

      <Modal title="Motivo da perda" open={negocioParaMarcarPerdido !== null} onClose={() => setNegocioParaMarcarPerdido(null)}>
        {negocioParaMarcarPerdido && (
          <div className="flex flex-col gap-3">
            <div className="text-[12px] text-muted">
              Por que "{negocioParaMarcarPerdido.negocio.nome}" foi perdido?
            </div>
            <Select value={motivoPerdaSelecionado} onChange={(event) => setMotivoPerdaSelecionado(event.target.value)}>
              {MOTIVOS_PERDA.map((motivo) => (
                <option key={motivo} value={motivo}>
                  {motivo}
                </option>
              ))}
            </Select>
            {motivoPerdaSelecionado === "Outro" && (
              <Textarea
                rows={3}
                value={motivoPerdaOutro}
                onChange={(event) => setMotivoPerdaOutro(event.target.value)}
                placeholder="Descreva o motivo"
                autoFocus
              />
            )}
            <div className="flex gap-2">
              <Button type="button" disabled={salvandoMotivoPerda} onClick={confirmarMotivoPerda}>
                {salvandoMotivoPerda ? "Salvando..." : "Confirmar"}
              </Button>
              <Button type="button" variant="ghost" onClick={() => setNegocioParaMarcarPerdido(null)}>
                Cancelar
              </Button>
            </div>
          </div>
        )}
      </Modal>
    </div>
  );
}
