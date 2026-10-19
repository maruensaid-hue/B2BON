// Production builds use the same-origin Worker proxy; local development keeps the configurable API URL.
export const API_BASE_URL = import.meta.env.PROD
  ? "/api/v1"
  : (import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000/api/v1");
const TOKEN_KEY = "b2bon_token";
const USUARIO_KEY = "b2bon_usuario";
const TEM_LICENCA_KEY = "b2bon_tem_licenca";
const DEMO_KEY = "b2bon_demo_expira_em";

// Remove JWTs left by older releases; requests now authenticate with HttpOnly cookies.
if (typeof window !== "undefined") localStorage.removeItem(TOKEN_KEY);

const MSG_SERVIDOR_INICIANDO =
  "Não foi possível conectar ao servidor agora. Se ele estava ocioso, pode levar até 2 minutos para iniciar — tente novamente em instantes.";
const MSG_RESPOSTA_INVALIDA = "Resposta inesperada do servidor. Atualize a página e tente novamente.";

export class ApiError extends Error {
  status: number;

  constructor(status: number, detalhe: string) {
    super(detalhe);
    this.status = status;
  }
}

/** Erros em que o servidor não respondeu (ocioso/iniciando): vale tentar de novo sozinho. */
export function servidorIniciando(error: unknown): boolean {
  return error instanceof ApiError && [0, 502, 503, 504].includes(error.status);
}

async function buscar(url: string, init: RequestInit): Promise<Response> {
  try {
    return await fetch(url, init);
  } catch (erro) {
    if (erro instanceof DOMException && erro.name === "AbortError") throw erro;
    throw new ApiError(0, MSG_SERVIDOR_INICIANDO);
  }
}

let apiAquecida = false;
/** A API gratuita dorme quando fica ociosa e leva até 2 minutos para acordar. Uma chamada leve ao abrir o login
 * começa a acordá-la enquanto a pessoa digita as credenciais. */
export function aquecerApi(): void {
  if (apiAquecida) return;
  apiAquecida = true;
  void fetch(`${API_BASE_URL}/planos`, { credentials: "omit" }).catch(() => undefined);
}

/** Mensagem para a tela: a do servidor quando é um erro da API, senão o texto padrão. */
export function mensagemErro(error: unknown, padrao: string): string {
  return error instanceof ApiError ? error.message : padrao;
}

/** Marca local para UX; o segredo de sessão fica no cookie HttpOnly do servidor. */
export function getToken(): string | null {
  return localStorage.getItem(USUARIO_KEY) ? "cookie-session" : null;
}

export function setSessao(_token: string, usuario: unknown, temLicencaAtiva: boolean = true): void {
  // Migra instalações antigas: nunca persiste o JWT acessível por JavaScript.
  localStorage.removeItem(TOKEN_KEY);
  localStorage.setItem(USUARIO_KEY, JSON.stringify(usuario));
  localStorage.setItem(TEM_LICENCA_KEY, JSON.stringify(temLicencaAtiva));
}

export function getTemLicencaAtiva(): boolean {
  const bruto = localStorage.getItem(TEM_LICENCA_KEY);
  if (!bruto) return true;
  try {
    return JSON.parse(bruto) as boolean;
  } catch {
    return true;
  }
}

/** Atualiza só a flag de licença ativa no localStorage, sem tocar token
 * nem usuário — usada quando o back reativa a licença no meio da sessão
 * (autoatendimento "já paguei", raio-X 2026-09-09), sem exigir logout/login. */
export function setTemLicencaAtiva(temLicencaAtiva: boolean): void {
  localStorage.setItem(TEM_LICENCA_KEY, JSON.stringify(temLicencaAtiva));
}

/** Atualiza o usuário salvo no localStorage sem tocar token/licença —
 * mesmo padrão de `setTemLicencaAtiva`, usada quando algum dado do
 * usuário muda no meio da sessão (raio-X 2026-09-14: aviso de template
 * do WhatsApp dispensado). */
export function atualizarUsuarioSalvo(usuario: unknown): void {
  localStorage.setItem(USUARIO_KEY, JSON.stringify(usuario));
}

export function limparSessao(): void {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USUARIO_KEY);
  localStorage.removeItem(TEM_LICENCA_KEY);
  localStorage.removeItem(DEMO_KEY);
}

/** D-082: sessão de demonstração (dados fictícios, expira sozinha) — guarda só a expiração para a faixa de aviso. */
export function setDemoExpiraEm(expiraEm: string | null): void {
  if (expiraEm) localStorage.setItem(DEMO_KEY, expiraEm);
  else localStorage.removeItem(DEMO_KEY);
}

export function getDemoExpiraEm(): string | null {
  return localStorage.getItem(DEMO_KEY);
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  return (await requestComHeaders<T>(path, options)).dados;
}

/** Chamada com cabeçalhos próprios (ex.: `X-Convite-Token` do portal do fornecedor, Phase F). */
export const requisitar = request;

/** Resposta de erro vira `ApiError` com a mensagem do backend. */
async function exigirSucesso(response: Response, token: string | null, mensagemPadrao: string): Promise<void> {
  if (response.status === 401) {
    // Só é "sessão expirada" se havia um token sendo usado — um 401 numa
    // chamada sem token (ex.: a própria tentativa de login) é só
    // credencial errada, e quem chamou precisa ver a mensagem real do
    // backend ("E-mail ou senha inválidos."), não um redirect enganoso.
    if (token) {
      limparSessao();
      if (window.location.pathname !== "/login") {
        window.location.href = "/login";
      }
      throw new ApiError(401, "Sessão expirada — faça login novamente.");
    }
    const corpo = await response.json().catch(() => ({}));
    throw new ApiError(401, corpo.detalhe ?? "Não foi possível autenticar.");
  }
  if (!response.ok) {
    const corpo = await response.json().catch(() => ({}));
    throw new ApiError(response.status, corpo.detalhe ?? mensagemPadrao);
  }
}

async function requestComHeaders<T>(path: string, options: RequestInit = {}): Promise<{ dados: T; headers: Headers }> {
  const token = getToken();
  const headers: HeadersInit = {
    "Content-Type": "application/json",
    ...options.headers,
  };

  const response = await buscar(`${API_BASE_URL}${path}`, { ...options, headers, credentials: "include" });

  await exigirSucesso(response, token, "Erro inesperado ao chamar a API.");

  if (response.status === 204) return { dados: undefined as T, headers: response.headers };
  const texto = await response.text();
  try {
    return { dados: JSON.parse(texto) as T, headers: response.headers };
  } catch {
    throw new ApiError(response.status, MSG_RESPOSTA_INVALIDA);
  }
}

/** Página de uma lista paginada por cursor (Fase S0): o próximo cursor vem
 * no header `X-Proximo-Cursor`; `null` = última página. */
export interface Pagina<T> {
  itens: T[];
  proximoCursor: string | null;
}

async function getPagina<T>(path: string, cursor?: string | null): Promise<Pagina<T>> {
  const separador = path.includes("?") ? "&" : "?";
  const url = cursor ? `${path}${separador}cursor=${encodeURIComponent(cursor)}` : path;
  const { dados, headers } = await requestComHeaders<T[]>(url);
  return { itens: dados, proximoCursor: headers.get("X-Proximo-Cursor") };
}

export const api = {
  get: <T,>(path: string, options?: { signal?: AbortSignal }) => request<T>(path, options),
  getPagina,
  post: <T,>(path: string, body?: unknown) =>
    request<T>(path, { method: "POST", body: body !== undefined ? JSON.stringify(body) : undefined }),
  put: <T,>(path: string, body?: unknown) =>
    request<T>(path, { method: "PUT", body: body !== undefined ? JSON.stringify(body) : undefined }),
  patch: <T,>(path: string, body?: unknown) =>
    request<T>(path, { method: "PATCH", body: body !== undefined ? JSON.stringify(body) : undefined }),
  delete: <T,>(path: string, body?: unknown) =>
    request<T>(path, { method: "DELETE", body: body !== undefined ? JSON.stringify(body) : undefined }),
};

/** Download binário (ex.: PDF) — não passa por `request()` porque a resposta não é JSON. */
export async function getBlob(path: string): Promise<Blob> {
  const token = getToken();
  const response = await buscar(`${API_BASE_URL}${path}`, {
    credentials: "include",
  });
  await exigirSucesso(response, token, "Não foi possível baixar o arquivo.");
  return response.blob();
}

async function _enviarMultipart<T>(path: string, formData: FormData): Promise<T> {
  const token = getToken();
  const response = await buscar(`${API_BASE_URL}${path}`, {
    method: "POST",
    credentials: "include",
    body: formData,
  });

  await exigirSucesso(response, token, "Não foi possível enviar o arquivo.");

  return (await response.json()) as T;
}

/** Upload de arquivo binário (ex.: PDF/DOCX de proposta) via multipart —
 * não passa por `request()` porque não pode forçar Content-Type:
 * application/json (o browser precisa definir o boundary do multipart
 * sozinho). `file` é opcional. */
export async function postFile<T>(
  path: string,
  file: File | null,
  camposExtras?: Record<string, string>,
): Promise<T> {
  const formData = new FormData();
  if (file) formData.append("arquivo", file);
  for (const [chave, valor] of Object.entries(camposExtras ?? {})) {
    formData.append(chave, valor);
  }
  return _enviarMultipart<T>(path, formData);
}

/** Mesma ideia de `postFile`, mas pra vários arquivos de uma vez (ex.:
 * carrossel de fotos de um post) — cada um vai como um campo `arquivos`
 * separado, casando com `arquivos: list[UploadFile]` do FastAPI. */
export async function postFiles<T>(
  path: string,
  files: File[],
  camposExtras?: Record<string, string>,
): Promise<T> {
  const formData = new FormData();
  for (const file of files) formData.append("arquivos", file);
  for (const [chave, valor] of Object.entries(camposExtras ?? {})) {
    formData.append(chave, valor);
  }
  return _enviarMultipart<T>(path, formData);
}
