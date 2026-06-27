"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { usePlaidLink } from "react-plaid-link";
import {
  createLinkToken,
  deleteConnector,
  disableConnector,
  disconnectConnectorAccount,
  enableConnectorSecret,
  exchangePublicToken,
  getConnector,
  listConnectors,
  setConnectorOAuthApp,
  startConnectorOAuth,
  syncConnector,
  testConnector,
  type ConnectorDetail,
  type ConnectorField,
  type ConnectorSummary,
} from "@/lib/api";

// ─── status + capability presentation ───────────────────────────────────────

interface StatusMeta {
  label: string;
  className: string;
  dot: string;
}

function statusMeta(status: string): StatusMeta {
  switch (status) {
    case "connected":
      return {
        label: "Connected",
        className: "bg-accent-soft text-accent",
        dot: "bg-accent",
      };
    case "connecting":
      return { label: "Connecting…", className: "bg-surface-muted text-muted", dot: "bg-muted" };
    case "error":
      return { label: "Error", className: "bg-[var(--danger)]/12 text-danger", dot: "bg-danger" };
    case "needs_reconnect":
      return {
        label: "Reconnect",
        className: "bg-[var(--danger)]/12 text-danger",
        dot: "bg-danger",
      };
    case "disabled":
      return { label: "Disabled", className: "bg-surface-muted text-muted", dot: "bg-muted" };
    default:
      return {
        label: "Available",
        className: "border border-border text-muted",
        dot: "bg-border",
      };
  }
}

const CAPABILITY_LABEL: Record<string, string> = {
  ingest: "Ingests data",
  tools: "Tools",
  channel: "Channel",
};

function StatusBadge({ status }: { status: string }) {
  const meta = statusMeta(status);
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium ${meta.className}`}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${meta.dot}`} />
      {meta.label}
    </span>
  );
}

function CapabilityChip({ name }: { name: string }) {
  return (
    <span className="rounded-md border border-border px-2 py-0.5 text-[11px] font-medium text-muted">
      {CAPABILITY_LABEL[name] ?? name}
    </span>
  );
}

// ─── card ────────────────────────────────────────────────────────────────────

function ConnectorCard({
  connector,
  index,
  onOpen,
}: {
  connector: ConnectorSummary;
  index: number;
  onOpen: (key: string) => void;
}) {
  return (
    <button
      type="button"
      onClick={() => onOpen(connector.key)}
      style={{ animationDelay: `${Math.min(index, 12) * 40}ms` }}
      className="pragya-rise group flex flex-col gap-3 rounded-2xl border border-border bg-surface p-5 text-left shadow-sm transition duration-200 hover:-translate-y-0.5 hover:border-accent/40 hover:shadow-md focus:outline-none focus-visible:ring-2 focus-visible:ring-accent/40"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="grid h-11 w-11 place-items-center rounded-xl bg-surface-muted text-2xl">
          {connector.icon}
        </div>
        <StatusBadge status={connector.status} />
      </div>
      <div className="space-y-1">
        <p className="text-[11px] font-medium uppercase tracking-wider text-muted">
          {connector.category}
        </p>
        <h3 className="font-serif text-lg leading-tight text-foreground">{connector.name}</h3>
      </div>
      <p className="line-clamp-2 text-sm text-muted">{connector.pitch}</p>
      <div className="mt-auto flex flex-wrap gap-1.5 pt-1">
        {connector.capabilities.map((c) => (
          <CapabilityChip key={c} name={c} />
        ))}
      </div>
    </button>
  );
}

// ─── config form field ───────────────────────────────────────────────────────

function FieldInput({
  field,
  value,
  configured,
  onChange,
}: {
  field: ConnectorField;
  value: string;
  configured: boolean;
  onChange: (key: string, value: string) => void;
}) {
  const base =
    "w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground outline-none transition focus:border-accent/60 focus:ring-2 focus:ring-accent/20";
  return (
    <label className="block space-y-1.5">
      <span className="flex items-center gap-2 text-sm font-medium text-foreground">
        {field.label}
        {!field.required && <span className="text-xs font-normal text-muted">optional</span>}
        {configured && (
          <span className="text-xs font-normal text-accent">configured ••••</span>
        )}
      </span>
      {field.type === "bool" ? (
        <select
          className={base}
          value={value || "false"}
          onChange={(e) => onChange(field.key, e.target.value)}
        >
          <option value="true">Yes</option>
          <option value="false">No</option>
        </select>
      ) : field.type === "select" ? (
        <select className={base} value={value} onChange={(e) => onChange(field.key, e.target.value)}>
          <option value="">Choose…</option>
          {field.options.map((o) => (
            <option key={o} value={o}>
              {o}
            </option>
          ))}
        </select>
      ) : (
        <input
          className={base}
          type={field.type === "secret" ? "password" : field.type === "number" ? "number" : "text"}
          value={value}
          placeholder={field.placeholder ?? (configured ? "•••••• (leave blank to keep)" : "")}
          onChange={(e) => onChange(field.key, e.target.value)}
        />
      )}
      {field.help && <span className="block text-xs text-muted">{field.help}</span>}
    </label>
  );
}

// ─── buttons ─────────────────────────────────────────────────────────────────

const PRIMARY =
  "inline-flex items-center justify-center gap-2 rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white transition hover:opacity-90 disabled:opacity-50";
const SECONDARY =
  "inline-flex items-center justify-center gap-2 rounded-lg border border-border px-4 py-2 text-sm font-medium text-foreground transition hover:bg-surface-muted disabled:opacity-50";
const DANGER =
  "inline-flex items-center justify-center gap-2 rounded-lg border border-[var(--danger)]/40 px-4 py-2 text-sm font-medium text-danger transition hover:bg-[var(--danger)]/10 disabled:opacity-50";

// ─── detail drawer ───────────────────────────────────────────────────────────

function DetailDrawer({
  detail,
  token,
  busy,
  onClose,
  onChanged,
  onError,
}: {
  detail: ConnectorDetail | null;
  token: string;
  busy: boolean;
  onClose: () => void;
  onChanged: () => void;
  onError: (message: string) => void;
}) {
  // Keyed by connector in the parent, so a lazy initializer (not an effect)
  // seeds the form from the schema defaults each time the drawer opens.
  const [form, setForm] = useState<Record<string, string>>(() => {
    const initial: Record<string, string> = {};
    for (const f of detail?.config_schema ?? []) {
      initial[f.key] = f.default === null || f.default === undefined ? "" : String(f.default);
    }
    return initial;
  });
  const [working, setWorking] = useState(false);

  const setField = useCallback((key: string, value: string) => {
    setForm((prev) => ({ ...prev, [key]: value }));
  }, []);

  // Plaid Link (managed_widget). These hooks run unconditionally (before the
  // null guard, per the rules of hooks); harmless for non-Plaid connectors —
  // linkToken stays null so Plaid Link is simply never ready.
  const [linkToken, setLinkToken] = useState<string | null>(null);
  const wantPlaidOpen = useRef(false);
  const onPlaidSuccess = useCallback(
    async (publicToken: string) => {
      if (detail === null) return;
      setWorking(true);
      try {
        await exchangePublicToken(publicToken, token);
        await enableConnectorSecret(detail.key, {}, token); // mark the connector connected
        onChanged();
      } catch (err) {
        onError(err instanceof Error ? err.message : "Could not connect the bank.");
      } finally {
        setWorking(false);
      }
    },
    [detail, token, onChanged, onError],
  );
  const { open: openPlaid, ready: plaidReady } = usePlaidLink({
    token: linkToken,
    onSuccess: onPlaidSuccess,
    onExit: () => setWorking(false),
  });
  useEffect(() => {
    if (plaidReady && wantPlaidOpen.current) {
      wantPlaidOpen.current = false;
      openPlaid();
    }
  }, [plaidReady, openPlaid]);

  if (detail === null) return null;
  const d = detail; // non-null binding for use inside nested closures

  const isConnected = detail.status === "connected";
  const isOAuth = detail.auth_kind === "oauth2";
  const hasAccounts = isOAuth && detail.accounts.length > 0;

  function buildConfig(): Record<string, unknown> {
    const out: Record<string, unknown> = {};
    for (const f of d.config_schema) {
      const raw = form[f.key] ?? "";
      if (raw === "") continue;
      out[f.key] = f.type === "number" ? Number(raw) : f.type === "bool" ? raw === "true" : raw;
    }
    return out;
  }

  async function run(action: () => Promise<unknown>) {
    setWorking(true);
    try {
      await action();
      onChanged();
    } catch (err) {
      onError(err instanceof Error ? err.message : "Something went wrong.");
    } finally {
      setWorking(false);
    }
  }

  async function connectOAuth() {
    setWorking(true);
    try {
      // First time: save the app creds server-side so future connects are one-click.
      if (!d.oauth_server_configured && form.client_id && form.client_secret) {
        await setConnectorOAuthApp(
          d.key,
          { client_id: form.client_id, client_secret: form.client_secret },
          token,
        );
      }
      const url = await startConnectorOAuth(d.key, buildConfig(), token);
      window.location.href = url; // hand off to the provider's consent screen
    } catch (err) {
      onError(err instanceof Error ? err.message : "Could not start the connection.");
      setWorking(false);
    }
  }

  // managed_widget (Plaid): fetch a link token, then the effect opens Plaid Link.
  async function connectPlaid() {
    setWorking(true);
    try {
      wantPlaidOpen.current = true;
      setLinkToken(await createLinkToken(token));
    } catch (err) {
      onError(err instanceof Error ? err.message : "Could not start Plaid.");
      setWorking(false);
    }
  }

  const disabled = working || busy;

  return (
    <div className="fixed inset-0 z-40 flex justify-end">
      <button
        type="button"
        aria-label="Close"
        onClick={onClose}
        className="pragya-fade-in absolute inset-0 bg-foreground/20 backdrop-blur-[2px]"
      />
      <aside className="pragya-slide-in pragya-scroll relative z-10 h-full w-full max-w-md overflow-y-auto border-l border-border bg-surface p-6 shadow-2xl">
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-center gap-3">
            <div className="grid h-12 w-12 place-items-center rounded-xl bg-surface-muted text-2xl">
              {detail.icon}
            </div>
            <div>
              <h2 className="font-serif text-xl text-foreground">{detail.name}</h2>
              <p className="text-xs uppercase tracking-wider text-muted">{detail.category}</p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close panel"
            className="rounded-md p-1.5 text-muted transition hover:bg-surface-muted hover:text-foreground"
          >
            ✕
          </button>
        </div>

        <div className="mt-4 flex flex-wrap items-center gap-2">
          <StatusBadge status={detail.status} />
          {detail.capabilities.map((c) => (
            <CapabilityChip key={c} name={c} />
          ))}
        </div>

        <p className="mt-4 text-sm text-muted">{detail.pitch}</p>

        {detail.last_error && (
          <p className="mt-4 rounded-lg border border-[var(--danger)]/30 bg-[var(--danger)]/10 px-3 py-2 text-sm text-danger">
            {detail.last_error}
          </p>
        )}

        {/* One-click note when the OAuth app is configured server-side. */}
        {!isConnected && isOAuth && detail.oauth_server_configured && (
          <p className="mt-6 text-sm text-muted">
            Pragya&apos;s Google app is configured — connect your account in one click.
          </p>
        )}

        {/* Setup / config form */}
        {(!isConnected || !isOAuth) && detail.config_schema.length > 0 && (
          <div className="mt-6 space-y-4">
            <h3 className="font-serif text-base text-foreground">
              {!isOAuth
                ? "Configuration"
                : detail.oauth_server_configured
                  ? "Options"
                  : "One-time setup"}
            </h3>
            {isOAuth && !detail.oauth_server_configured && (
              <p className="text-xs text-muted">
                Create an OAuth client once in your provider console, then paste its credentials
                here.{" "}
                {detail.docs_url && (
                  <a
                    href={detail.docs_url}
                    target="_blank"
                    rel="noreferrer"
                    className="text-accent underline"
                  >
                    Setup guide →
                  </a>
                )}
              </p>
            )}
            {detail.config_schema.map((f) => (
              <FieldInput
                key={f.key}
                field={f}
                value={form[f.key] ?? ""}
                configured={detail.configured_fields.includes(f.key)}
                onChange={setField}
              />
            ))}
          </div>
        )}

        {/* Linked accounts for OAuth connectors (multi-account) */}
        {hasAccounts && (
          <div className="mt-6">
            <h3 className="font-serif text-base text-foreground">Connected accounts</h3>
            <ul className="mt-2 space-y-2">
              {detail.accounts.map((a) => (
                <li
                  key={a.id}
                  className="flex items-center justify-between gap-3 rounded-lg border border-border bg-surface-muted/40 px-3 py-2"
                >
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium text-foreground">{a.label}</p>
                    <div className="mt-1">
                      <StatusBadge status={a.status} />
                    </div>
                  </div>
                  <button
                    type="button"
                    className="shrink-0 rounded-md px-2.5 py-1 text-xs font-medium text-danger transition hover:bg-[var(--danger)]/10 disabled:opacity-50"
                    disabled={disabled}
                    onClick={() => run(() => disconnectConnectorAccount(detail.key, a.id, token))}
                  >
                    Disconnect
                  </button>
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Granted scopes for connected OAuth */}
        {isConnected && isOAuth && detail.granted_scopes.length > 0 && (
          <div className="mt-6">
            <h3 className="font-serif text-base text-foreground">Access granted</h3>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {detail.granted_scopes.map((s) => (
                <span
                  key={s}
                  className="rounded-md bg-surface-muted px-2 py-1 text-[11px] text-muted"
                >
                  {s.replace(/^https:\/\/www\.googleapis\.com\/auth\//, "")}
                </span>
              ))}
            </div>
          </div>
        )}

        {detail.last_sync_at && (
          <p className="mt-4 text-xs text-muted">
            Last synced {new Date(detail.last_sync_at).toLocaleString()}
          </p>
        )}

        {/* Actions */}
        <div className="mt-6 flex flex-wrap gap-2">
          {isOAuth && (!isConnected || hasAccounts) && (
            <button type="button" className={PRIMARY} disabled={disabled} onClick={connectOAuth}>
              {hasAccounts
                ? "Add another account"
                : `${detail.oauth_server_configured ? "Connect" : "Save & connect"} ${detail.name}`}
            </button>
          )}
          {!isConnected && !isOAuth && detail.auth_kind !== "managed_widget" && (
            <button
              type="button"
              className={PRIMARY}
              disabled={disabled}
              onClick={() => run(() => enableConnectorSecret(detail.key, buildConfig(), token))}
            >
              {detail.auth_kind === "none" ? `Enable ${detail.name}` : "Save & connect"}
            </button>
          )}
          {!isConnected && detail.auth_kind === "managed_widget" && (
            <button type="button" className={PRIMARY} disabled={disabled} onClick={connectPlaid}>
              Connect with Plaid
            </button>
          )}
          {isConnected && (
            <>
              {detail.capabilities.includes("ingest") && (
                <button
                  type="button"
                  className={SECONDARY}
                  disabled={disabled}
                  onClick={() => run(() => syncConnector(detail.key, token))}
                >
                  Sync now
                </button>
              )}
              <button
                type="button"
                className={SECONDARY}
                disabled={disabled}
                onClick={() => run(() => testConnector(detail.key, token))}
              >
                Test
              </button>
              {isOAuth && !hasAccounts && (
                <button type="button" className={SECONDARY} disabled={disabled} onClick={connectOAuth}>
                  Reconnect
                </button>
              )}
              <button
                type="button"
                className={SECONDARY}
                disabled={disabled}
                onClick={() => run(() => disableConnector(detail.key, token))}
              >
                Disable
              </button>
            </>
          )}
          {(isConnected || detail.status === "error" || detail.status === "needs_reconnect") && (
            <button
              type="button"
              className={DANGER}
              disabled={disabled}
              onClick={() => run(() => deleteConnector(detail.key, token))}
            >
              Remove
            </button>
          )}
        </div>
      </aside>
    </div>
  );
}

// ─── marketplace ─────────────────────────────────────────────────────────────

interface Flash {
  kind: "success" | "error";
  message: string;
}

export function Connectors({ token }: { token: string }) {
  const [connectors, setConnectors] = useState<ConnectorSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState<string>("All");
  const [selected, setSelected] = useState<ConnectorDetail | null>(null);
  const [drawerBusy, setDrawerBusy] = useState(false);
  const [flash, setFlash] = useState<Flash | null>(() => {
    if (typeof window === "undefined") return null;
    const status = new URLSearchParams(window.location.search).get("status");
    if (status === "connected") return { kind: "success", message: "Connected successfully." };
    if (status === "error") {
      return { kind: "error", message: "The connection could not be completed." };
    }
    return null;
  });

  const refresh = useCallback(async () => {
    try {
      setConnectors(await listConnectors(token));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load connectors.");
    } finally {
      setLoading(false);
    }
  }, [token]);

  const openDetail = useCallback(
    async (key: string) => {
      setDrawerBusy(true);
      try {
        setSelected(await getConnector(key, token));
      } catch (err) {
        setError(err instanceof Error ? err.message : "Could not open that connector.");
      } finally {
        setDrawerBusy(false);
      }
    },
    [token],
  );

  // Initial load + OAuth-return handling (?connector=&status=). The flash is
  // seeded in the useState initializer above; here we just open the connector
  // that was connected and clean the URL.
  useEffect(() => {
    void (async () => {
      await refresh();
      if (typeof window === "undefined") return;
      const params = new URLSearchParams(window.location.search);
      const connector = params.get("connector");
      if (params.get("status") === "connected" && connector) await openDetail(connector);
      if (params.get("status")) {
        window.history.replaceState({}, "", window.location.pathname);
      }
    })();
  }, [refresh, openDetail]);

  const categories = useMemo(() => {
    const set = new Set(connectors.map((c) => c.category));
    return ["All", ...Array.from(set).sort()];
  }, [connectors]);

  const visible = useMemo(() => {
    const q = query.trim().toLowerCase();
    return connectors.filter((c) => {
      const matchesQuery =
        !q || c.name.toLowerCase().includes(q) || c.pitch.toLowerCase().includes(q);
      const matchesCategory = category === "All" || c.category === category;
      return matchesQuery && matchesCategory;
    });
  }, [connectors, query, category]);

  const connectedCount = connectors.filter((c) => c.status === "connected").length;

  async function onChanged() {
    await refresh();
    if (selected) {
      try {
        setSelected(await getConnector(selected.key, token));
      } catch {
        setSelected(null);
      }
    }
  }

  return (
    <div className="flex h-full flex-col bg-background">
      <header className="sticky top-0 z-10 border-b border-border bg-surface/80 px-6 py-4 backdrop-blur">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h1 className="font-serif text-2xl text-foreground">Connectors</h1>
            <p className="mt-0.5 text-sm text-muted">
              Bring your world into Pragya — {connectedCount} connected of {connectors.length}.
            </p>
          </div>
          <input
            type="search"
            placeholder="Search connectors…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            className="w-56 rounded-full border border-border bg-background px-4 py-2 text-sm text-foreground outline-none transition focus:border-accent/60 focus:ring-2 focus:ring-accent/20"
          />
        </div>
        <div className="mt-3 flex flex-wrap gap-1.5">
          {categories.map((c) => (
            <button
              key={c}
              type="button"
              onClick={() => setCategory(c)}
              className={`rounded-full px-3 py-1 text-xs font-medium transition ${
                category === c
                  ? "bg-foreground text-background"
                  : "border border-border text-muted hover:bg-surface-muted"
              }`}
            >
              {c}
            </button>
          ))}
        </div>
      </header>

      {flash && (
        <div
          className={`mx-6 mt-4 rounded-lg px-4 py-2 text-sm ${
            flash.kind === "success"
              ? "bg-accent-soft text-accent"
              : "bg-[var(--danger)]/10 text-danger"
          }`}
        >
          {flash.message}
        </div>
      )}
      {error && (
        <div className="mx-6 mt-4 rounded-lg bg-[var(--danger)]/10 px-4 py-2 text-sm text-danger">
          {error}
        </div>
      )}

      <div className="pragya-scroll flex-1 overflow-y-auto px-6 py-6">
        {loading ? (
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {Array.from({ length: 6 }).map((_, i) => (
              <div
                key={i}
                className="h-44 animate-pulse rounded-2xl border border-border bg-surface-muted/40"
              />
            ))}
          </div>
        ) : visible.length === 0 ? (
          <p className="py-16 text-center text-sm text-muted">No connectors match your search.</p>
        ) : (
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {visible.map((c, i) => (
              <ConnectorCard key={c.key} connector={c} index={i} onOpen={openDetail} />
            ))}
          </div>
        )}
      </div>

      {selected && (
        <DetailDrawer
          key={selected.key}
          detail={selected}
          token={token}
          busy={drawerBusy}
          onClose={() => setSelected(null)}
          onChanged={onChanged}
          onError={(message) => setFlash({ kind: "error", message })}
        />
      )}
    </div>
  );
}
