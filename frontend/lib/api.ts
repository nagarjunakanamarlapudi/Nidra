/**
 * Typed client for the Pragya backend API.
 *
 * The base URL is read from `NEXT_PUBLIC_API_BASE` and falls back to
 * `http://localhost:8000` when unset. All calls are authenticated with a
 * single-user bearer token.
 */

const DEFAULT_API_BASE = "http://localhost:8000";

/** A successful reply from the assistant. */
export interface ChatResponse {
  /** The assistant's message. */
  reply: string;
  /** The conversation this reply belongs to; pass it back on the next turn. */
  conversationId: number;
}

/** Shape of the JSON returned by `POST /chat`. */
interface ChatApiResponse {
  reply: string;
  conversation_id: number;
}

/** Reasoning effort for a turn; omit for the model's default. */
export type Effort = "low" | "medium" | "high";

/** Arguments for {@link sendChat}. */
export interface SendChatArgs {
  /** The user's message. */
  message: string;
  /** Existing conversation id, omitted on the first turn. */
  conversationId?: number;
  /** Single-user access token sent as `Authorization: Bearer <token>`. */
  token: string;
  /** Override the API base URL (defaults to the env var / localhost). */
  apiBase?: string;
  /** Reasoning effort for this turn; omit for the model's default. */
  effort?: Effort;
}

/** Resolve the effective API base URL. */
export function resolveApiBase(apiBase?: string): string {
  return apiBase ?? process.env.NEXT_PUBLIC_API_BASE ?? DEFAULT_API_BASE;
}

/**
 * Send a chat message to the backend and return the assistant's reply.
 *
 * Throws a descriptive {@link Error} on any non-2xx response. A 401 is
 * special-cased to a friendly "Unauthorized" message so the UI can prompt the
 * user to re-enter their token.
 */
export async function sendChat(args: SendChatArgs): Promise<ChatResponse> {
  const { message, conversationId, token, apiBase, effort } = args;
  const base = resolveApiBase(apiBase);

  const body: { message: string; conversation_id?: number; effort?: Effort } = { message };
  if (conversationId !== undefined) {
    body.conversation_id = conversationId;
  }
  if (effort !== undefined) {
    body.effort = effort;
  }

  let response: Response;
  try {
    response = await fetch(`${base}/chat`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify(body),
    });
  } catch (cause) {
    throw new Error(
      `Could not reach the assistant at ${base}. Is the backend running?`,
      { cause },
    );
  }

  if (response.status === 401) {
    throw new Error("Unauthorized: check your access token");
  }

  if (!response.ok) {
    const detail = await readErrorDetail(response);
    throw new Error(
      `Chat request failed (${response.status})${detail ? `: ${detail}` : ""}`,
    );
  }

  const data = (await response.json()) as ChatApiResponse;
  return { reply: data.reply, conversationId: data.conversation_id };
}

/** A past conversation, for the history sidebar. */
export interface ConversationSummary {
  id: number;
  title: string;
  createdAt: string;
}

/** A role + text within a conversation. */
export interface ConversationMessage {
  role: "user" | "assistant";
  content: string;
}

/** A conversation with its full message history. */
export interface ConversationDetail {
  id: number;
  messages: ConversationMessage[];
}

/** List past conversations, newest first. */
export async function listConversations(
  token: string,
  apiBase?: string,
): Promise<ConversationSummary[]> {
  const data = await getJson<{ id: number; title: string; created_at: string }[]>(
    "/conversations",
    token,
    apiBase,
  );
  return data.map((c) => ({ id: c.id, title: c.title, createdAt: c.created_at }));
}

/** Load a single conversation's messages. */
export async function getConversation(
  id: number,
  token: string,
  apiBase?: string,
): Promise<ConversationDetail> {
  const data = await getJson<{ id: number; messages: { role: string; content: string }[] }>(
    `/conversations/${id}`,
    token,
    apiBase,
  );
  return {
    id: data.id,
    messages: data.messages.map((m) => ({
      role: m.role === "assistant" ? "assistant" : "user",
      content: m.content,
    })),
  };
}

/** Authenticated GET returning parsed JSON, with the same error handling as {@link sendChat}. */
async function getJson<T>(path: string, token: string, apiBase?: string): Promise<T> {
  const base = resolveApiBase(apiBase);
  let response: Response;
  try {
    response = await fetch(`${base}${path}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
  } catch (cause) {
    throw new Error(
      `Could not reach the assistant at ${base}. Is the backend running?`,
      { cause },
    );
  }
  if (response.status === 401) {
    throw new Error("Unauthorized: check your access token");
  }
  if (!response.ok) {
    const detail = await readErrorDetail(response);
    throw new Error(`Request failed (${response.status})${detail ? `: ${detail}` : ""}`);
  }
  return (await response.json()) as T;
}

/** A stored daily digest. */
export interface Digest {
  id: number;
  content: string;
  delivered: string;
  createdAt: string;
}

interface DigestApi {
  id: number;
  content: string;
  delivered: string;
  created_at: string;
}

function toDigest(d: DigestApi): Digest {
  return { id: d.id, content: d.content, delivered: d.delivered, createdAt: d.created_at };
}

/** List recent digests, newest first. */
export async function listDigests(token: string, apiBase?: string): Promise<Digest[]> {
  return (await getJson<DigestApi[]>("/digests", token, apiBase)).map(toDigest);
}

/** Generate a digest now (manual trigger). */
export async function runDigest(token: string, apiBase?: string): Promise<Digest> {
  return toDigest(await postJson<DigestApi>("/digests/run", token, apiBase));
}

/** Authenticated POST (no body) returning parsed JSON. */
async function postJson<T>(path: string, token: string, apiBase?: string): Promise<T> {
  const base = resolveApiBase(apiBase);
  let response: Response;
  try {
    response = await fetch(`${base}${path}`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
    });
  } catch (cause) {
    throw new Error(
      `Could not reach the assistant at ${base}. Is the backend running?`,
      { cause },
    );
  }
  if (response.status === 401) {
    throw new Error("Unauthorized: check your access token");
  }
  if (!response.ok) {
    const detail = await readErrorDetail(response);
    throw new Error(`Request failed (${response.status})${detail ? `: ${detail}` : ""}`);
  }
  return (await response.json()) as T;
}

/** Authenticated POST with a JSON body, returning parsed JSON. */
async function postJsonBody<T>(
  path: string,
  body: unknown,
  token: string,
  apiBase?: string,
): Promise<T> {
  const base = resolveApiBase(apiBase);
  let response: Response;
  try {
    response = await fetch(`${base}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
      body: JSON.stringify(body),
    });
  } catch (cause) {
    throw new Error(
      `Could not reach the assistant at ${base}. Is the backend running?`,
      { cause },
    );
  }
  if (response.status === 401) {
    throw new Error("Unauthorized: check your access token");
  }
  if (!response.ok) {
    const detail = await readErrorDetail(response);
    throw new Error(`Request failed (${response.status})${detail ? `: ${detail}` : ""}`);
  }
  return (await response.json()) as T;
}

// ─── Finance / Plaid ──────────────────────────────────────────────────────────

/** A bank account returned by `GET /finance/accounts`. */
export interface FinanceAccount {
  account_id: number;
  item_id: number;
  institution: string;
  institution_logo: string | null;
  institution_color: string | null;
  name: string;
  official_name: string | null;
  mask: string | null;
  type: string;
  subtype: string | null;
  current_balance: string | null;
  iso_currency: string | null;
}

/**
 * Create a Plaid Link token (`POST /finance/link/token`).
 * Returns the `link_token` string to hand to `usePlaidLink`.
 */
export async function createLinkToken(token: string, apiBase?: string): Promise<string> {
  const data = await postJson<{ link_token: string }>("/finance/link/token", token, apiBase);
  return data.link_token;
}

/**
 * Exchange a Plaid public token for a persistent item (`POST /finance/link/exchange`).
 * Returns the institution name from the backend response.
 */
export async function exchangePublicToken(
  publicToken: string,
  token: string,
  apiBase?: string,
): Promise<string> {
  const data = await postJsonBody<{ institution: string }>(
    "/finance/link/exchange",
    { public_token: publicToken },
    token,
    apiBase,
  );
  return data.institution;
}

/**
 * List all connected bank accounts (`GET /finance/accounts`).
 */
export async function listAccounts(token: string, apiBase?: string): Promise<FinanceAccount[]> {
  return getJson<FinanceAccount[]>("/finance/accounts", token, apiBase);
}

/**
 * Trigger a Plaid sync to pull the latest transactions and balances
 * (`POST /finance/sync`). Returns after the sync completes.
 */
export async function syncFinance(token: string, apiBase?: string): Promise<void> {
  await postJson<unknown>("/finance/sync", token, apiBase);
}

/**
 * Disconnect (remove) a Plaid Item, revoking it from Plaid and deleting all
 * local data (`DELETE /finance/items/{itemId}`).
 *
 * Throws a descriptive Error on any non-2xx response.
 */
export async function disconnectInstitution(
  itemId: number,
  token: string,
  apiBase?: string,
): Promise<void> {
  const base = resolveApiBase(apiBase);
  let response: Response;
  try {
    response = await fetch(`${base}/finance/items/${itemId}`, {
      method: "DELETE",
      headers: { Authorization: `Bearer ${token}` },
    });
  } catch (cause) {
    throw new Error(
      `Could not reach the assistant at ${base}. Is the backend running?`,
      { cause },
    );
  }
  if (response.status === 401) {
    throw new Error("Unauthorized: check your access token");
  }
  if (!response.ok) {
    const detail = await readErrorDetail(response);
    throw new Error(
      `Disconnect failed (${response.status})${detail ? `: ${detail}` : ""}`,
    );
  }
}

/** A holding returned by `GET /finance/holdings`. */
export interface Holding {
  account_id: number;
  security_id: string | null;
  ticker: string | null;
  security_name: string;
  quantity: string;
  price: string | null;
  value: string | null;
  iso_currency: string | null;
  cost_basis: string | null;
  lots: Array<{ quantity: string | number; cost_basis: string | number | null; acquired_date: string | null }> | null;
}

/**
 * List all investment holdings across all linked accounts,
 * sorted by value desc (`GET /finance/holdings`).
 */
export async function listHoldings(token: string, apiBase?: string): Promise<Holding[]> {
  return getJson<Holding[]>("/finance/holdings", token, apiBase);
}

/** A bank/credit transaction (`GET /finance/transactions/{account_id}`). */
export interface BankTransaction {
  id: number;
  date: string;
  name: string;
  merchant_name: string | null;
  amount: string;
  category: string | null;
  pending: boolean;
}

/** An investment transaction — trade or dividend (`GET /finance/investment-transactions/...`). */
export interface InvestmentTransaction {
  id: number;
  date: string;
  name: string;
  type: string;
  subtype: string | null;
  ticker: string | null;
  security_id: string | null;
  quantity: string;
  price: string | null;
  amount: string;
}

/** Bank/credit transactions for one account, newest first. */
export async function listAccountTransactions(
  accountId: number,
  token: string,
  apiBase?: string,
): Promise<BankTransaction[]> {
  return getJson<BankTransaction[]>(`/finance/transactions/${accountId}`, token, apiBase);
}

/** Investment transactions (trades/dividends) for one account, newest first. */
export async function listInvestmentTransactions(
  accountId: number,
  token: string,
  apiBase?: string,
): Promise<InvestmentTransaction[]> {
  return getJson<InvestmentTransaction[]>(
    `/finance/investment-transactions/${accountId}`,
    token,
    apiBase,
  );
}

/** Investment transactions for one security (a holding), newest first. */
export async function listHoldingTransactions(
  securityId: string,
  token: string,
  apiBase?: string,
): Promise<InvestmentTransaction[]> {
  return getJson<InvestmentTransaction[]>(
    `/finance/holdings/${securityId}/transactions`,
    token,
    apiBase,
  );
}

// ─── FX rate ─────────────────────────────────────────────────────────────────

/** USD→INR exchange rate returned by `GET /finance/fx`. */
export interface FxRate {
  usd_inr: number | null;
  as_of: string | null;
}

/**
 * Fetch the current USD→INR exchange rate (cached ~12 h server-side).
 * Returns null fields when the backend has no rate yet.
 */
export async function getFx(token: string, apiBase?: string): Promise<FxRate> {
  return getJson<FxRate>("/finance/fx", token, apiBase);
}

// ─── Connectors ───────────────────────────────────────────────────────────────

/** A configurable field in a connector's setup form. */
export interface ConnectorField {
  key: string;
  label: string;
  type: string;
  required: boolean;
  help: string | null;
  placeholder: string | null;
  options: string[];
  default: string | number | boolean | null;
}

/** One linked account on an OAuth connector (e.g. a single Gmail address). */
export interface ConnectorAccount {
  id: number;
  label: string;
  status: string;
  granted_scopes: string[];
}

/** A connector as shown in the marketplace gallery (no secret values). */
export interface ConnectorSummary {
  key: string;
  name: string;
  category: string;
  pitch: string;
  icon: string;
  capabilities: string[];
  auth_kind: string;
  widget: string | null;
  status: string;
  enabled: boolean;
  last_sync_at: string | null;
  last_error: string | null;
  granted_scopes: string[];
  configured_fields: string[];
  /** True when the OAuth client creds are configured server-side (env) — the
   * UI then offers a pure one-click connect with no client-id/secret fields. */
  oauth_server_configured: boolean;
  /** Linked accounts (non-empty only for OAuth connectors that have any). */
  accounts: ConnectorAccount[];
}

/** A connector's full detail, including its config schema. */
export interface ConnectorDetail extends ConnectorSummary {
  config_schema: ConnectorField[];
  docs_url: string | null;
}

/** List every available connector with its live status. */
export async function listConnectors(
  token: string,
  apiBase?: string,
): Promise<ConnectorSummary[]> {
  return getJson<ConnectorSummary[]>("/connectors", token, apiBase);
}

/** Fetch one connector's detail (config schema + status). */
export async function getConnector(
  key: string,
  token: string,
  apiBase?: string,
): Promise<ConnectorDetail> {
  return getJson<ConnectorDetail>(`/connectors/${key}`, token, apiBase);
}

/** Enable a secret-auth connector with the given config. */
export async function enableConnectorSecret(
  key: string,
  config: Record<string, unknown>,
  token: string,
  apiBase?: string,
): Promise<ConnectorDetail> {
  return postJsonBody<ConnectorDetail>(`/connectors/${key}/enable`, { config }, token, apiBase);
}

/** Begin an OAuth connect: returns the provider authorize URL to redirect to. */
export async function startConnectorOAuth(
  key: string,
  config: Record<string, unknown>,
  token: string,
  apiBase?: string,
): Promise<string> {
  const data = await postJsonBody<{ authorize_url: string }>(
    `/connectors/${key}/oauth/start`,
    { config },
    token,
    apiBase,
  );
  return data.authorize_url;
}

/**
 * Save the shared OAuth *app* credentials (client id/secret) server-side, once.
 * Afterwards connecting is one-click (no fields). Returns the refreshed detail.
 */
export async function setConnectorOAuthApp(
  key: string,
  creds: { client_id: string; client_secret: string },
  token: string,
  apiBase?: string,
): Promise<ConnectorDetail> {
  return postJsonBody<ConnectorDetail>(`/connectors/${key}/oauth/app`, creds, token, apiBase);
}

/** Trigger an immediate sync for an ingest connector. */
export async function syncConnector(
  key: string,
  token: string,
  apiBase?: string,
): Promise<{ items: number }> {
  return postJson<{ items: number }>(`/connectors/${key}/sync`, token, apiBase);
}

/** Probe a connector's connectivity. */
export async function testConnector(
  key: string,
  token: string,
  apiBase?: string,
): Promise<{ ok: boolean; detail: string | null }> {
  return postJson<{ ok: boolean; detail: string | null }>(
    `/connectors/${key}/test`,
    token,
    apiBase,
  );
}

/** Disable a connector (keeps its stored config; can be re-enabled). */
export async function disableConnector(
  key: string,
  token: string,
  apiBase?: string,
): Promise<ConnectorDetail> {
  return postJson<ConnectorDetail>(`/connectors/${key}/disable`, token, apiBase);
}

/** Remove a connector entirely, deleting its stored config. */
export async function deleteConnector(
  key: string,
  token: string,
  apiBase?: string,
): Promise<void> {
  const base = resolveApiBase(apiBase);
  let response: Response;
  try {
    response = await fetch(`${base}/connectors/${key}`, {
      method: "DELETE",
      headers: { Authorization: `Bearer ${token}` },
    });
  } catch (cause) {
    throw new Error(`Could not reach the assistant at ${base}. Is the backend running?`, { cause });
  }
  if (response.status === 401) {
    throw new Error("Unauthorized: check your access token");
  }
  if (!response.ok) {
    const detail = await readErrorDetail(response);
    throw new Error(`Remove failed (${response.status})${detail ? `: ${detail}` : ""}`);
  }
}

/**
 * Disconnect a single linked account from an OAuth connector
 * (`DELETE /connectors/{key}/accounts/{accountId}`). Returns the refreshed
 * connector detail with the account removed.
 */
export async function disconnectConnectorAccount(
  key: string,
  accountId: number,
  token: string,
  apiBase?: string,
): Promise<ConnectorDetail> {
  const base = resolveApiBase(apiBase);
  let response: Response;
  try {
    response = await fetch(`${base}/connectors/${key}/accounts/${accountId}`, {
      method: "DELETE",
      headers: { Authorization: `Bearer ${token}` },
    });
  } catch (cause) {
    throw new Error(`Could not reach the assistant at ${base}. Is the backend running?`, { cause });
  }
  if (response.status === 401) {
    throw new Error("Unauthorized: check your access token");
  }
  if (!response.ok) {
    const detail = await readErrorDetail(response);
    throw new Error(`Disconnect failed (${response.status})${detail ? `: ${detail}` : ""}`);
  }
  return (await response.json()) as ConnectorDetail;
}

// ─── helpers ──────────────────────────────────────────────────────────────────

/** Best-effort extraction of an error message from a failed response. */
async function readErrorDetail(response: Response): Promise<string | null> {
  try {
    const data: unknown = await response.json();
    if (data && typeof data === "object" && "detail" in data) {
      const detail = (data as { detail: unknown }).detail;
      if (typeof detail === "string") {
        return detail;
      }
    }
    return null;
  } catch {
    return null;
  }
}
