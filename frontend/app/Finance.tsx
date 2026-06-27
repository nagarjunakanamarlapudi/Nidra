"use client";
import {
  type Dispatch,
  type SetStateAction,
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";
import { usePlaidLink } from "react-plaid-link";
import {
  createLinkToken,
  disconnectInstitution,
  exchangePublicToken,
  getFx,
  listAccountTransactions,
  listAccounts,
  listHoldings,
  listHoldingTransactions,
  listInvestmentTransactions,
  syncFinance,
  type BankTransaction,
  type FinanceAccount,
  type FxRate,
  type Holding,
  type InvestmentTransaction,
} from "../lib/api";
import {
  USD,
  formatBalance,
  isDebt,
  computeNetWorth,
  groupByItemId,
} from "../lib/finance-format";

// ── Inline sub-components ────────────────────────────────────────────────────

function InstitutionBadge({
  institution,
  logo,
  color,
}: {
  institution: string;
  logo: string | null;
  color: string | null;
}) {
  if (logo) {
    return (
      // eslint-disable-next-line @next/next/no-img-element
      <img
        src={`data:image/png;base64,${logo}`}
        alt={institution}
        width={20}
        height={20}
        className="h-5 w-5 rounded-full object-contain"
      />
    );
  }
  const letter = institution.charAt(0).toUpperCase();
  return (
    <span
      aria-label={institution}
      className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[10px] font-semibold text-white${color ? "" : " bg-accent"}`}
      style={color ? { backgroundColor: color } : undefined}
    >
      {letter}
    </span>
  );
}

function TypeChip({ type }: { type: string }) {
  const label =
    type === "investment"
      ? "BROKERAGE"
      : type === "depository"
        ? "BANK"
        : type.toUpperCase();
  return (
    <span className="ml-2 rounded-full bg-surface-muted px-2 py-0.5 text-[11px] uppercase tracking-wide text-muted">
      {label}
    </span>
  );
}

function Money({ raw }: { raw: string | null }) {
  if (raw == null) return <span className="text-muted">—</span>;
  const amt = Number(raw);
  const display = USD.format(-amt);
  const glyph = amt < 0 ? "▲" : amt > 0 ? "▼" : "";
  const cls =
    amt < 0 ? "text-green-600" : amt > 0 ? "text-danger" : "text-muted";
  return (
    <span className={`tabular-nums ${cls}`}>
      {glyph} {display}
    </span>
  );
}

function GainLoss({
  dollars,
  pct,
}: {
  dollars: number | null;
  pct: number | null;
}) {
  if (dollars == null) return <span className="text-muted">—</span>;
  const pos = dollars >= 0;
  const cls = pos ? "text-green-600" : "text-danger";
  const glyph = pos ? "▲" : "▼";
  return (
    <span className={`tabular-nums ${cls}`}>
      {glyph} {pos ? "+" : ""}
      {USD.format(dollars)}
      {pct != null ? ` (${pos ? "+" : ""}${pct.toFixed(1)}%)` : ""}
    </span>
  );
}

// ── INR formatting ───────────────────────────────────────────────────────────

const INR = new Intl.NumberFormat("en-IN", {
  style: "currency",
  currency: "INR",
  maximumFractionDigits: 0,
});

function toInr(usdAmount: number, rate: number): string {
  return INR.format(usdAmount * rate);
}

// ── Default account selection ────────────────────────────────────────────────

function computeDefaultAccountId(
  accs: FinanceAccount[],
  hs: Holding[],
): number | null {
  if (accs.length === 0) return null;
  try {
    const stored = localStorage.getItem("finance:selectedAccountId");
    if (stored) {
      const id = Number(stored);
      if (accs.some((a) => a.account_id === id)) return id;
    }
  } catch {
    // localStorage unavailable (SSR or private browsing)
  }
  // Highest-value investment account
  const investAccounts = accs.filter((a) => a.type === "investment");
  if (investAccounts.length > 0) {
    const withValue = investAccounts.map((a) => ({
      a,
      total: hs
        .filter((h) => h.account_id === a.account_id)
        .reduce((s, h) => s + Number(h.value ?? 0), 0),
    }));
    withValue.sort((x, y) => y.total - x.total);
    return withValue[0].a.account_id;
  }
  // Highest-balance non-debt account
  const nonDebt = accs.filter((a) => !isDebt(a.type));
  if (nonDebt.length > 0) {
    nonDebt.sort(
      (x, y) =>
        Number(y.current_balance ?? 0) - Number(x.current_balance ?? 0),
    );
    return nonDebt[0].account_id;
  }
  return accs[0].account_id;
}

// ── Main component ───────────────────────────────────────────────────────────

export function Finance({ token }: { token: string }) {
  const [linkToken, setLinkToken] = useState<string | null>(null);
  const [accounts, setAccounts] = useState<FinanceAccount[]>([]);
  const [holdings, setHoldings] = useState<Holding[]>([]);
  const [fxRate, setFxRate] = useState<FxRate | null>(null);
  const [accountsLoading, setAccountsLoading] = useState(true);
  const [connecting, setConnecting] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [disconnecting, setDisconnecting] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [lastSynced, setLastSynced] = useState<Date | null>(null);

  const [selectedAccountId, setSelectedAccountId] = useState<number | null>(
    null,
  );
  const [activeTab, setActiveTab] = useState<
    "holdings" | "activity" | "transactions"
  >("holdings");
  const [selectedSecurityKey, setSelectedSecurityKey] = useState<string | null>(
    null,
  );

  const [sortCol, setSortCol] = useState<
    "ticker" | "qty" | "price" | "value" | "gain"
  >("value");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");
  const [holdingsFilter, setHoldingsFilter] = useState("");
  const [txnFilter, setTxnFilter] = useState("");
  const [railFilter, setRailFilter] = useState("");

  const [txnCache, setTxnCache] = useState<
    Map<number, BankTransaction[] | InvestmentTransaction[]>
  >(new Map());
  const [tradesCache, setTradesCache] = useState<
    Map<string, InvestmentTransaction[]>
  >(new Map());

  const [isWide, setIsWide] = useState(() => {
    if (typeof window === "undefined") return false;
    return window.matchMedia("(min-width: 1280px)").matches;
  });

  // Lazy-load state for the detail panel
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);

  // Track inspector slide-over open state (used for <1280px)
  const [inspectorOpen, setInspectorOpen] = useState(false);

  const railFilterRef = useRef<HTMLInputElement>(null);
  const holdingsFilterRef = useRef<HTMLInputElement>(null);
  const txnFilterRef = useRef<HTMLInputElement>(null);

  // ── Viewport tracking ──────────────────────────────────────────────────────

  useEffect(() => {
    const mq = window.matchMedia("(min-width: 1280px)");
    const handler = (e: MediaQueryListEvent) => setIsWide(e.matches);
    mq.addEventListener("change", handler);
    return () => mq.removeEventListener("change", handler);
  }, []);

  // ── Data load on mount ─────────────────────────────────────────────────────

  const refresh = useCallback(async () => {
    try {
      const [accs, hs] = await Promise.all([
        listAccounts(token),
        listHoldings(token),
      ]);
      setAccounts(accs);
      setHoldings(hs);
    } catch {
      // Non-fatal: keep existing list
    }
  }, [token]);

  useEffect(() => {
    let active = true;
    void (async () => {
      try {
        const [accs, hs, lt] = await Promise.all([
          listAccounts(token),
          listHoldings(token),
          createLinkToken(token),
        ]);
        if (active) {
          setAccounts(accs);
          setHoldings(hs);
          setLinkToken(lt);
          // Set default selection
          const defaultId = computeDefaultAccountId(accs, hs);
          setSelectedAccountId(defaultId);
          if (defaultId != null) {
            const acc = accs.find((a) => a.account_id === defaultId);
            setActiveTab(acc?.type === "investment" ? "holdings" : "transactions");
          }
        }
      } catch {
        // If link-token fails, still show accounts
      } finally {
        if (active) setAccountsLoading(false);
      }
    })();
    // Non-fatal FX fetch — runs independently so it doesn't block account load.
    void (async () => {
      try {
        const fx = await getFx(token);
        if (active) setFxRate(fx);
      } catch {
        // FX is best-effort; no error shown to user
      }
    })();
    return () => {
      active = false;
    };
  }, [token]);

  // ── Lazy-load transactions when account changes ────────────────────────────

  useEffect(() => {
    if (selectedAccountId == null) return;
    if (txnCache.has(selectedAccountId)) return;
    const selectedAccount = accounts.find(
      (a) => a.account_id === selectedAccountId,
    );
    if (!selectedAccount) return;
    const isInvestmentAccount = selectedAccount.type === "investment";

    let active = true;
    void (async () => {
      setDetailLoading(true);
      setDetailError(null);
      try {
        let data: BankTransaction[] | InvestmentTransaction[];
        if (isInvestmentAccount) {
          data = await listInvestmentTransactions(selectedAccountId, token);
        } else {
          data = await listAccountTransactions(selectedAccountId, token);
        }
        if (active) {
          setTxnCache((prev) => new Map(prev).set(selectedAccountId, data));
        }
      } catch (err) {
        if (active) {
          setDetailError(
            err instanceof Error ? err.message : "Failed to load transactions.",
          );
        }
      } finally {
        if (active) setDetailLoading(false);
      }
    })();
    return () => {
      active = false;
    };
  }, [selectedAccountId, accounts, token, txnCache]);

  // ── Esc key to close inspector ─────────────────────────────────────────────

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setSelectedSecurityKey(null);
        setInspectorOpen(false);
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);

  // ── / key to focus filter ──────────────────────────────────────────────────

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (
        e.key === "/" &&
        !(e.target instanceof HTMLInputElement) &&
        !(e.target instanceof HTMLTextAreaElement)
      ) {
        e.preventDefault();
        railFilterRef.current?.focus();
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);

  // ── Plaid wiring ───────────────────────────────────────────────────────────

  const onPlaidSuccess = useCallback(
    async (publicToken: string) => {
      setError(null);
      try {
        await exchangePublicToken(publicToken, token);
        await refresh();
        const lt = await createLinkToken(token);
        setLinkToken(lt);
      } catch (err) {
        setError(
          err instanceof Error
            ? err.message
            : "Failed to connect the bank account.",
        );
      }
    },
    [token, refresh],
  );

  const { open, ready } = usePlaidLink({
    token: linkToken,
    onSuccess: onPlaidSuccess,
  });

  async function handleConnect() {
    if (ready) {
      open();
      return;
    }
    setConnecting(true);
    setError(null);
    try {
      const lt = await createLinkToken(token);
      setLinkToken(lt);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Could not prepare bank connection.",
      );
    } finally {
      setConnecting(false);
    }
  }

  async function handleSync() {
    setSyncing(true);
    setError(null);
    try {
      await syncFinance(token);
      // Clear caches after sync
      setTxnCache(new Map());
      setTradesCache(new Map());
      setLastSynced(new Date());
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Sync failed.");
    } finally {
      setSyncing(false);
    }
  }

  async function handleDisconnect(itemId: number, institutionName: string) {
    if (
      !globalThis.confirm(
        `Disconnect ${institutionName}? This removes it from Pragya and frees a slot.`,
      )
    ) {
      return;
    }
    setDisconnecting(itemId);
    setError(null);
    try {
      await disconnectInstitution(itemId, token);
      await refresh();
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to disconnect the bank.",
      );
    } finally {
      setDisconnecting(null);
    }
  }

  function selectAccount(id: number) {
    if (id === selectedAccountId) return;
    setSelectedAccountId(id);
    setSelectedSecurityKey(null);
    setInspectorOpen(false);
    setSortCol("value");
    setSortDir("desc");
    setHoldingsFilter("");
    setTxnFilter("");
    try {
      localStorage.setItem("finance:selectedAccountId", String(id));
    } catch {
      // localStorage unavailable
    }
    const acc = accounts.find((a) => a.account_id === id);
    setActiveTab(acc?.type === "investment" ? "holdings" : "transactions");
  }

  // ── Derived values ─────────────────────────────────────────────────────────

  const netWorth = computeNetWorth(accounts);
  const totalAssets = accounts.reduce((s, a) => {
    if (isDebt(a.type)) return s;
    const n = Number(a.current_balance ?? 0);
    return isNaN(n) ? s : s + n;
  }, 0);
  const totalDebts = accounts.reduce((s, a) => {
    if (!isDebt(a.type)) return s;
    const n = Number(a.current_balance ?? 0);
    return isNaN(n) ? s : s + n;
  }, 0);

  const institutionGroups = groupByItemId(accounts);
  const hasAccounts = accounts.length > 0;

  const selectedAccount =
    accounts.find((a) => a.account_id === selectedAccountId) ?? null;
  const isInvestment = selectedAccount?.type === "investment";

  const accountHoldings = holdings
    .filter((h) => h.account_id === selectedAccountId)
    .sort((x, y) =>
      x.value != null && y.value != null
        ? Number(y.value) - Number(x.value)
        : x.value == null
          ? 1
          : -1,
    );

  // Gain/loss across all holdings with cost_basis
  const holdingsWithCostBasis = accountHoldings.filter(
    (h) => h.cost_basis != null,
  );
  const totalGain = holdingsWithCostBasis.reduce(
    (s, h) => s + (Number(h.value ?? 0) - Number(h.cost_basis ?? 0)),
    0,
  );
  const totalCost = holdingsWithCostBasis.reduce(
    (s, h) => s + Number(h.cost_basis ?? 0),
    0,
  );
  const hasPartialCostBasis =
    holdingsWithCostBasis.length < accountHoldings.length &&
    accountHoldings.length > 0;

  // Rail filter
  const filteredGroups = railFilter.trim()
    ? institutionGroups
        .map(
          ([itemId, accs]) =>
            [
              itemId,
              accs.filter(
                (a) =>
                  (a.official_name ?? a.name)
                    .toLowerCase()
                    .includes(railFilter.toLowerCase()) ||
                  a.institution
                    .toLowerCase()
                    .includes(railFilter.toLowerCase()),
              ),
            ] as [number, FinanceAccount[]],
        )
        .filter(([, accs]) => accs.length > 0)
    : institutionGroups;

  // Holdings sort + filter
  const filteredHoldings = holdingsFilter.trim()
    ? accountHoldings.filter(
        (h) =>
          (h.ticker ?? "")
            .toLowerCase()
            .includes(holdingsFilter.toLowerCase()) ||
          h.security_name
            .toLowerCase()
            .includes(holdingsFilter.toLowerCase()),
      )
    : accountHoldings;

  const sortedHoldings = [...filteredHoldings].sort((a, b) => {
    let cmp = 0;
    if (sortCol === "ticker")
      cmp = (a.ticker ?? a.security_name).localeCompare(
        b.ticker ?? b.security_name,
      );
    else if (sortCol === "qty")
      cmp = Number(a.quantity) - Number(b.quantity);
    else if (sortCol === "price")
      cmp = Number(a.price ?? 0) - Number(b.price ?? 0);
    else if (sortCol === "value")
      cmp = Number(a.value ?? 0) - Number(b.value ?? 0);
    else if (sortCol === "gain") {
      const ga =
        a.value != null && a.cost_basis != null
          ? Number(a.value) - Number(a.cost_basis)
          : -Infinity;
      const gb =
        b.value != null && b.cost_basis != null
          ? Number(b.value) - Number(b.cost_basis)
          : -Infinity;
      cmp = ga - gb;
    }
    return sortDir === "asc" ? cmp : -cmp;
  });

  function toggleSort(col: typeof sortCol) {
    if (sortCol === col) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortCol(col);
      setSortDir("desc");
    }
  }

  function ariaSortFor(
    col: typeof sortCol,
  ): "ascending" | "descending" | "none" {
    if (sortCol !== col) return "none";
    return sortDir === "asc" ? "ascending" : "descending";
  }

  // Txn data from cache
  const rawTxns =
    selectedAccountId != null
      ? (txnCache.get(selectedAccountId) ?? null)
      : null;
  const bankTxns: BankTransaction[] | null =
    !isInvestment && rawTxns != null ? (rawTxns as BankTransaction[]) : null;
  const investTxns: InvestmentTransaction[] | null =
    isInvestment && rawTxns != null
      ? (rawTxns as InvestmentTransaction[])
      : null;

  const filteredBankTxns = bankTxns
    ? txnFilter.trim()
      ? bankTxns.filter(
          (t) =>
            (t.merchant_name ?? t.name)
              .toLowerCase()
              .includes(txnFilter.toLowerCase()) ||
            (t.category ?? "").toLowerCase().includes(txnFilter.toLowerCase()),
        )
      : bankTxns
    : null;

  const filteredInvestTxns = investTxns
    ? txnFilter.trim()
      ? investTxns.filter((t) =>
          (t.ticker ?? t.name).toLowerCase().includes(txnFilter.toLowerCase()),
        )
      : investTxns
    : null;

  // Inspector holding
  const inspectorHolding =
    selectedSecurityKey != null
      ? (accountHoldings.find(
          (h) =>
            h.security_id === selectedSecurityKey ||
            h.security_name === selectedSecurityKey,
        ) ?? null)
      : null;

  // ── Render ─────────────────────────────────────────────────────────────────

  if (accountsLoading) {
    return (
      <div className="flex h-full flex-col bg-background">
        <div className="space-y-3 p-6">
          {[80, 100, 60].map((w) => (
            <div
              key={w}
              className="h-4 animate-pulse rounded bg-border"
              style={{ width: `${w}%` }}
            />
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-full min-h-0 flex-col bg-background">
      {/* ── STICKY HEADER ─────────────────────────────────────────────────── */}
      <header className="sticky top-0 z-20 flex flex-wrap items-center justify-between gap-x-6 gap-y-1 border-b border-border bg-surface px-6 py-3">
        <div>
          <h1 className="font-serif text-2xl text-foreground">Finance</h1>
          {hasAccounts && (
            <div className="mt-0.5 flex items-baseline gap-4">
              <div>
                <span
                  className={`font-serif text-3xl tabular-nums tracking-tight ${netWorth < 0 ? "text-danger" : "text-foreground"}`}
                >
                  {USD.format(netWorth)}
                </span>
                {fxRate?.usd_inr != null && (
                  <span className="ml-2 text-sm tabular-nums text-muted">
                    {toInr(netWorth, fxRate.usd_inr)}
                  </span>
                )}
              </div>
              <div className="flex flex-col gap-0.5">
                <span className="text-xs text-muted">
                  Assets {USD.format(totalAssets)} · Debts {USD.format(totalDebts)}
                </span>
                {fxRate?.usd_inr != null && fxRate.as_of != null && (
                  <span className="text-[11px] text-muted">
                    1 USD = ₹{Number(fxRate.usd_inr).toLocaleString("en-IN")} · as of {fxRate.as_of}
                  </span>
                )}
              </div>
            </div>
          )}
        </div>
        <div className="flex items-center gap-2">
          {lastSynced && (
            <span className="hidden text-[11px] text-muted sm:inline">
              Synced{" "}
              {lastSynced.toLocaleTimeString([], {
                hour: "2-digit",
                minute: "2-digit",
              })}
            </span>
          )}
          {hasAccounts && (
            <button
              type="button"
              onClick={handleSync}
              disabled={syncing}
              className="rounded-lg border border-border bg-surface px-3 py-1.5 text-sm font-medium text-foreground transition hover:border-accent disabled:cursor-not-allowed disabled:opacity-50"
            >
              {syncing ? "Syncing…" : "Sync"}
            </button>
          )}
          <button
            type="button"
            onClick={handleConnect}
            disabled={connecting || (!!linkToken && !ready)}
            className="rounded-lg bg-accent px-4 py-1.5 text-sm font-medium text-white transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {connecting ? "Connecting…" : "Connect"}
          </button>
        </div>
      </header>

      {/* ── GLOBAL ERROR ──────────────────────────────────────────────────── */}
      {error && (
        <div
          role="alert"
          className="border-b border-danger/30 bg-danger/10 px-6 py-2 text-sm text-danger"
        >
          {error}
        </div>
      )}

      {/* ── BODY ──────────────────────────────────────────────────────────── */}
      {!hasAccounts ? (
        <div className="flex flex-1 items-center justify-center p-8">
          <div className="rounded-xl border border-border bg-surface p-8 text-center shadow-sm">
            <p className="font-serif text-lg text-foreground">
              No accounts connected yet
            </p>
            <p className="mt-1.5 text-sm text-muted">
              Connect a bank to see your balances and net worth here.
            </p>
          </div>
        </div>
      ) : (
        <div className="flex min-h-0 flex-1">
          {/* ── ACCOUNT RAIL ──────────────────────────────────────────────── */}
          <aside className="hidden w-[300px] shrink-0 flex-col border-r border-border bg-surface-muted/40 lg:flex">
            {/* Rail filter */}
            <div className="border-b border-border px-3 py-2">
              <input
                ref={railFilterRef}
                type="search"
                placeholder="Filter accounts…"
                value={railFilter}
                onChange={(e) => setRailFilter(e.target.value)}
                className="w-full rounded-md border border-border bg-surface px-2.5 py-1 text-xs text-foreground placeholder:text-muted focus:outline-none focus:ring-1 focus:ring-accent"
              />
            </div>
            {/* Account list */}
            <div
              role="listbox"
              aria-label="Accounts"
              className="pragya-scroll flex-1 overflow-y-auto"
              onKeyDown={(e) => {
                const opts = Array.from(
                  e.currentTarget.querySelectorAll<HTMLElement>(
                    '[role="option"]',
                  ),
                );
                const idx = opts.findIndex(
                  (el) =>
                    el.dataset.accountId === String(selectedAccountId),
                );
                if (e.key === "ArrowDown" && idx < opts.length - 1) {
                  e.preventDefault();
                  opts[idx + 1].focus();
                } else if (e.key === "ArrowUp" && idx > 0) {
                  e.preventDefault();
                  opts[idx - 1].focus();
                }
              }}
            >
              {filteredGroups.map(([itemId, accs]) => {
                const institutionName = accs[0]?.institution ?? "Unknown";
                const logo = accs[0]?.institution_logo ?? null;
                const color = accs[0]?.institution_color ?? null;
                return (
                  <div key={itemId}>
                    {/* Institution header */}
                    <div className="flex items-center gap-2 border-b border-border/60 px-3 py-2">
                      <InstitutionBadge
                        institution={institutionName}
                        logo={logo}
                        color={color}
                      />
                      <span className="flex-1 truncate text-xs font-semibold text-foreground">
                        {institutionName}
                      </span>
                      {disconnecting !== itemId ? (
                        <button
                          type="button"
                          onClick={() =>
                            handleDisconnect(
                              itemId,
                              institutionName,
                            ).catch(() => {})
                          }
                          className="shrink-0 text-[10px] text-muted transition hover:text-danger"
                          disabled={disconnecting != null}
                        >
                          Disconnect
                        </button>
                      ) : (
                        <span className="text-[10px] text-muted">
                          Removing…
                        </span>
                      )}
                    </div>
                    {/* Account rows */}
                    {accs.map((a) => {
                      const selected = a.account_id === selectedAccountId;
                      const debt = isDebt(a.type);
                      const balance = Number(a.current_balance ?? 0);
                      return (
                        <button
                          key={a.account_id}
                          role="option"
                          aria-selected={selected}
                          data-account-id={a.account_id}
                          type="button"
                          onClick={() => selectAccount(a.account_id)}
                          onKeyDown={(e) => {
                            if (e.key === "Enter" || e.key === " ") {
                              e.preventDefault();
                              selectAccount(a.account_id);
                            }
                          }}
                          className={[
                            "flex w-full items-center justify-between gap-2 px-3 py-2.5 text-left transition",
                            selected
                              ? "bg-accent/10 text-accent"
                              : "hover:bg-surface",
                          ].join(" ")}
                        >
                          <span className="min-w-0">
                            <span className="flex items-center">
                              <span className="truncate text-sm text-foreground">
                                {a.official_name ?? a.name}
                                {a.mask ? ` ···· ${a.mask}` : ""}
                              </span>
                              <TypeChip type={a.type} />
                            </span>
                            <span className="block text-[11px] capitalize text-muted">
                              {a.subtype ?? a.type}
                            </span>
                          </span>
                          <span className="shrink-0 text-right">
                            <span
                              className={[
                                "block text-xs tabular-nums",
                                debt
                                  ? balance > 0
                                    ? "text-danger"
                                    : "text-muted"
                                  : balance < 0
                                    ? "text-danger"
                                    : "text-foreground",
                              ].join(" ")}
                            >
                              {formatBalance(
                                a.current_balance,
                                a.iso_currency,
                              )}
                            </span>
                            {fxRate?.usd_inr != null &&
                              a.current_balance != null &&
                              (a.iso_currency == null || a.iso_currency === "USD") && (
                                <span className="block text-[10px] tabular-nums text-muted">
                                  {toInr(Math.abs(balance), fxRate.usd_inr)}
                                </span>
                              )}
                          </span>
                        </button>
                      );
                    })}
                  </div>
                );
              })}
            </div>
          </aside>

          {/* ── DETAIL PANEL ────────────────────────────────────────────── */}
          <section className="relative flex min-w-0 flex-1 flex-col">
            {selectedAccount == null ? (
              <div className="flex flex-1 items-center justify-center text-sm text-muted">
                Select an account ↑ ↓
              </div>
            ) : (
              <div className="flex min-h-0 flex-1">
                {/* Detail + optional inspector split */}
                <div className="flex min-w-0 flex-1 flex-col">
                  {/* Account header */}
                  <div className="border-b border-border px-6 py-4">
                    <div className="flex items-center gap-3">
                      <InstitutionBadge
                        institution={selectedAccount.institution}
                        logo={selectedAccount.institution_logo}
                        color={selectedAccount.institution_color}
                      />
                      <div className="min-w-0 flex-1">
                        <h2 className="truncate text-base font-semibold text-foreground">
                          {selectedAccount.official_name ??
                            selectedAccount.name}
                          {selectedAccount.mask
                            ? ` ···· ${selectedAccount.mask}`
                            : ""}
                        </h2>
                        <p className="text-xs capitalize text-muted">
                          {selectedAccount.institution} ·{" "}
                          {selectedAccount.subtype ?? selectedAccount.type}
                        </p>
                      </div>
                      <div className="shrink-0 text-right">
                        <p className="font-serif text-xl tabular-nums text-foreground">
                          {formatBalance(
                            selectedAccount.current_balance,
                            selectedAccount.iso_currency,
                          )}
                        </p>
                        {fxRate?.usd_inr != null &&
                          selectedAccount.current_balance != null &&
                          (selectedAccount.iso_currency == null ||
                            selectedAccount.iso_currency === "USD") && (
                            <p className="text-xs tabular-nums text-muted">
                              {toInr(
                                Math.abs(Number(selectedAccount.current_balance)),
                                fxRate.usd_inr,
                              )}
                            </p>
                          )}
                        {isInvestment && accountHoldings.length > 0 && (
                          <p className="text-xs text-muted">
                            <GainLoss
                              dollars={
                                holdingsWithCostBasis.length > 0
                                  ? totalGain
                                  : null
                              }
                              pct={
                                holdingsWithCostBasis.length > 0 &&
                                totalCost !== 0
                                  ? (totalGain / totalCost) * 100
                                  : null
                              }
                            />
                            {hasPartialCostBasis && (
                              <span className="ml-1 text-muted">
                                (partial)
                              </span>
                            )}
                          </p>
                        )}
                      </div>
                    </div>

                    {/* Tab bar (only for investment accounts) */}
                    {isInvestment && (
                      <div
                        role="tablist"
                        className="mt-3 flex gap-1"
                        onKeyDown={(e) => {
                          const tabs: Array<"holdings" | "activity"> = [
                            "holdings",
                            "activity",
                          ];
                          const idx = tabs.indexOf(
                            activeTab as "holdings" | "activity",
                          );
                          if (e.key === "ArrowRight" && idx < tabs.length - 1) {
                            setActiveTab(tabs[idx + 1]);
                          } else if (e.key === "ArrowLeft" && idx > 0) {
                            setActiveTab(tabs[idx - 1]);
                          }
                        }}
                      >
                        {(
                          [
                            { key: "holdings" as const, label: "Holdings" },
                            { key: "activity" as const, label: "Activity" },
                          ] as const
                        ).map(({ key, label }) => (
                          <button
                            key={key}
                            role="tab"
                            aria-selected={activeTab === key}
                            type="button"
                            onClick={() => setActiveTab(key)}
                            className={[
                              "rounded-md px-3 py-1 text-sm font-medium transition",
                              activeTab === key
                                ? "bg-accent-soft text-accent"
                                : "text-muted hover:bg-surface-muted hover:text-foreground",
                            ].join(" ")}
                          >
                            {label}
                          </button>
                        ))}
                      </div>
                    )}
                  </div>

                  {/* Tab content */}
                  <div
                    role="tabpanel"
                    className="pragya-scroll min-h-0 flex-1 overflow-y-auto"
                  >
                    {isInvestment && activeTab === "holdings" && (
                      <>
                        {/* Holdings filter */}
                        <div className="border-b border-border px-4 py-2">
                          <input
                            ref={holdingsFilterRef}
                            type="search"
                            placeholder="Filter holdings…"
                            value={holdingsFilter}
                            onChange={(e) =>
                              setHoldingsFilter(e.target.value)
                            }
                            className="w-full rounded-md border border-border bg-surface px-2.5 py-1 text-xs text-foreground placeholder:text-muted focus:outline-none focus:ring-1 focus:ring-accent"
                          />
                        </div>
                        {/* Holdings table */}
                        {sortedHoldings.length === 0 ? (
                          <p className="p-8 text-center text-sm text-muted">
                            {holdingsFilter
                              ? "No holdings match the filter."
                              : "No holdings reported for this account."}
                          </p>
                        ) : (
                          <div className="overflow-x-auto">
                            <table className="w-full text-sm">
                              <thead>
                                <tr className="border-b border-border bg-surface-muted/60 text-[11px] uppercase tracking-wider text-muted">
                                  <th
                                    className="cursor-pointer px-4 py-2 text-left"
                                    aria-sort={ariaSortFor("ticker")}
                                    onClick={() => toggleSort("ticker")}
                                  >
                                    Ticker{" "}
                                    {sortCol === "ticker"
                                      ? sortDir === "asc"
                                        ? "▲"
                                        : "▼"
                                      : ""}
                                  </th>
                                  {!selectedSecurityKey && (
                                    <th className="px-4 py-2 text-left">
                                      Name
                                    </th>
                                  )}
                                  <th
                                    className="cursor-pointer px-4 py-2 text-right"
                                    aria-sort={ariaSortFor("qty")}
                                    onClick={() => toggleSort("qty")}
                                  >
                                    Qty{" "}
                                    {sortCol === "qty"
                                      ? sortDir === "asc"
                                        ? "▲"
                                        : "▼"
                                      : ""}
                                  </th>
                                  {!selectedSecurityKey && (
                                    <th
                                      className="cursor-pointer px-4 py-2 text-right"
                                      aria-sort={ariaSortFor("price")}
                                      onClick={() => toggleSort("price")}
                                    >
                                      Price{" "}
                                      {sortCol === "price"
                                        ? sortDir === "asc"
                                          ? "▲"
                                          : "▼"
                                        : ""}
                                    </th>
                                  )}
                                  <th
                                    className="cursor-pointer px-4 py-2 text-right"
                                    aria-sort={ariaSortFor("value")}
                                    onClick={() => toggleSort("value")}
                                  >
                                    Value{" "}
                                    {sortCol === "value"
                                      ? sortDir === "asc"
                                        ? "▲"
                                        : "▼"
                                      : ""}
                                  </th>
                                  {!selectedSecurityKey && (
                                    <th className="px-4 py-2 text-right">
                                      Cost Basis
                                    </th>
                                  )}
                                  <th
                                    className="cursor-pointer px-4 py-2 text-right"
                                    aria-sort={ariaSortFor("gain")}
                                    onClick={() => toggleSort("gain")}
                                  >
                                    Gain/Loss{" "}
                                    {sortCol === "gain"
                                      ? sortDir === "asc"
                                        ? "▲"
                                        : "▼"
                                      : ""}
                                  </th>
                                </tr>
                              </thead>
                              <tbody className="divide-y divide-border/40">
                                {sortedHoldings.map((h, i) => {
                                  const key =
                                    h.security_id ?? h.security_name;
                                  const selected =
                                    selectedSecurityKey === key;
                                  const gainLoss =
                                    h.value != null && h.cost_basis != null
                                      ? Number(h.value) -
                                        Number(h.cost_basis)
                                      : null;
                                  const gainPct =
                                    gainLoss !== null &&
                                    h.cost_basis != null &&
                                    Number(h.cost_basis) !== 0
                                      ? (gainLoss / Number(h.cost_basis)) *
                                        100
                                      : null;
                                  const canOpen =
                                    h.security_id != null ||
                                    (h.lots != null && h.lots.length > 0);
                                  return (
                                    <tr
                                      key={`${key}-${i}`}
                                      aria-selected={selected}
                                      tabIndex={0}
                                      onClick={() => {
                                        if (!canOpen) return;
                                        if (selected) {
                                          setSelectedSecurityKey(null);
                                          setInspectorOpen(false);
                                        } else {
                                          setSelectedSecurityKey(key);
                                          setInspectorOpen(true);
                                        }
                                      }}
                                      onKeyDown={(e) => {
                                        if (
                                          canOpen &&
                                          (e.key === "Enter" ||
                                            e.key === " ")
                                        ) {
                                          e.preventDefault();
                                          if (selected) {
                                            setSelectedSecurityKey(null);
                                            setInspectorOpen(false);
                                          } else {
                                            setSelectedSecurityKey(key);
                                            setInspectorOpen(true);
                                          }
                                        }
                                        const rows =
                                          e.currentTarget
                                            .closest("tbody")
                                            ?.querySelectorAll<HTMLElement>(
                                              "tr",
                                            ) ?? [];
                                        if (
                                          e.key === "ArrowDown" &&
                                          i < rows.length - 1
                                        ) {
                                          e.preventDefault();
                                          rows[i + 1].focus();
                                        } else if (
                                          e.key === "ArrowUp" &&
                                          i > 0
                                        ) {
                                          e.preventDefault();
                                          rows[i - 1].focus();
                                        }
                                      }}
                                      className={[
                                        "transition",
                                        canOpen
                                          ? "cursor-pointer hover:bg-surface"
                                          : "",
                                        selected ? "bg-accent/10" : "",
                                      ].join(" ")}
                                    >
                                      <td className="px-4 py-2.5 font-medium text-foreground">
                                        {h.ticker ?? "—"}
                                      </td>
                                      {!selectedSecurityKey && (
                                        <td className="max-w-[180px] truncate px-4 py-2.5 text-muted">
                                          {h.security_name}
                                        </td>
                                      )}
                                      <td className="px-4 py-2.5 text-right tabular-nums text-foreground">
                                        {Number(h.quantity).toFixed(
                                          Number(h.quantity) % 1 === 0
                                            ? 0
                                            : 3,
                                        )}
                                      </td>
                                      {!selectedSecurityKey && (
                                        <td className="px-4 py-2.5 text-right tabular-nums text-foreground">
                                          {h.price != null
                                            ? USD.format(Number(h.price))
                                            : "—"}
                                        </td>
                                      )}
                                      <td className="px-4 py-2.5 text-right tabular-nums text-foreground">
                                        {h.value != null
                                          ? USD.format(Number(h.value))
                                          : "—"}
                                        {fxRate?.usd_inr != null &&
                                          h.value != null && (
                                            <span className="block text-[10px] text-muted">
                                              {toInr(
                                                Number(h.value),
                                                fxRate.usd_inr,
                                              )}
                                            </span>
                                          )}
                                      </td>
                                      {!selectedSecurityKey && (
                                        <td className="px-4 py-2.5 text-right tabular-nums text-muted">
                                          {h.cost_basis != null
                                            ? USD.format(
                                                Number(h.cost_basis),
                                              )
                                            : "—"}
                                        </td>
                                      )}
                                      <td className="px-4 py-2.5 text-right">
                                        <GainLoss
                                          dollars={gainLoss}
                                          pct={gainPct}
                                        />
                                      </td>
                                    </tr>
                                  );
                                })}
                              </tbody>
                            </table>
                          </div>
                        )}
                      </>
                    )}

                    {isInvestment && activeTab === "activity" && (
                      <>
                        {/* Activity filter */}
                        <div className="border-b border-border px-4 py-2">
                          <input
                            ref={txnFilterRef}
                            type="search"
                            placeholder="Filter activity…"
                            value={txnFilter}
                            onChange={(e) => setTxnFilter(e.target.value)}
                            className="w-full rounded-md border border-border bg-surface px-2.5 py-1 text-xs text-foreground placeholder:text-muted focus:outline-none focus:ring-1 focus:ring-accent"
                          />
                        </div>
                        {detailLoading ? (
                          <div className="space-y-2 p-4">
                            {[1, 2, 3].map((i) => (
                              <div
                                key={i}
                                className="h-8 animate-pulse rounded bg-border"
                              />
                            ))}
                          </div>
                        ) : detailError ? (
                          <p className="p-4 text-sm text-danger">
                            {detailError}
                          </p>
                        ) : filteredInvestTxns == null ||
                          filteredInvestTxns.length === 0 ? (
                          <p className="p-8 text-center text-sm text-muted">
                            No transactions yet.
                          </p>
                        ) : (
                          <>
                            <div className="overflow-x-auto">
                              <table className="w-full text-sm">
                                <thead>
                                  <tr className="border-b border-border bg-surface-muted/60 text-[11px] uppercase tracking-wider text-muted">
                                    <th className="px-4 py-2 text-left">
                                      Date
                                    </th>
                                    <th className="px-4 py-2 text-left">
                                      Ticker
                                    </th>
                                    <th className="px-4 py-2 text-left">
                                      Action
                                    </th>
                                    <th className="px-4 py-2 text-right">
                                      Qty
                                    </th>
                                    <th className="px-4 py-2 text-right">
                                      Amount
                                    </th>
                                  </tr>
                                </thead>
                                <tbody className="divide-y divide-border/40">
                                  {filteredInvestTxns.map((t) => (
                                    <tr
                                      key={t.id}
                                      className="hover:bg-surface"
                                    >
                                      <td className="px-4 py-2.5 tabular-nums text-muted">
                                        {t.date}
                                      </td>
                                      <td className="px-4 py-2.5 font-medium text-foreground">
                                        {t.ticker ?? "—"}
                                      </td>
                                      <td className="px-4 py-2.5 capitalize text-foreground">
                                        {t.subtype ?? t.type}
                                      </td>
                                      <td className="px-4 py-2.5 text-right tabular-nums text-foreground">
                                        {t.quantity}
                                      </td>
                                      <td className="px-4 py-2.5 text-right">
                                        <Money raw={t.amount} />
                                      </td>
                                    </tr>
                                  ))}
                                </tbody>
                              </table>
                            </div>
                            <p className="px-4 py-2 text-[11px] text-muted">
                              Showing {filteredInvestTxns.length} most recent
                            </p>
                          </>
                        )}
                      </>
                    )}

                    {!isInvestment && (
                      <>
                        {/* Txn filter */}
                        <div className="border-b border-border px-4 py-2">
                          <input
                            ref={txnFilterRef}
                            type="search"
                            placeholder="Filter transactions…"
                            value={txnFilter}
                            onChange={(e) => setTxnFilter(e.target.value)}
                            className="w-full rounded-md border border-border bg-surface px-2.5 py-1 text-xs text-foreground placeholder:text-muted focus:outline-none focus:ring-1 focus:ring-accent"
                          />
                        </div>
                        {detailLoading ? (
                          <div className="space-y-2 p-4">
                            {[1, 2, 3].map((i) => (
                              <div
                                key={i}
                                className="h-8 animate-pulse rounded bg-border"
                              />
                            ))}
                          </div>
                        ) : detailError ? (
                          <p className="p-4 text-sm text-danger">
                            {detailError}
                          </p>
                        ) : filteredBankTxns == null ||
                          filteredBankTxns.length === 0 ? (
                          <p className="p-8 text-center text-sm text-muted">
                            No transactions yet.
                          </p>
                        ) : (
                          <>
                            <div className="overflow-x-auto">
                              <table className="w-full text-sm">
                                <thead>
                                  <tr className="border-b border-border bg-surface-muted/60 text-[11px] uppercase tracking-wider text-muted">
                                    <th className="px-4 py-2 text-left">
                                      Date
                                    </th>
                                    <th className="px-4 py-2 text-left">
                                      Merchant / Name
                                    </th>
                                    <th className="px-4 py-2 text-left">
                                      Category
                                    </th>
                                    <th className="px-4 py-2 text-left">
                                      Status
                                    </th>
                                    <th className="px-4 py-2 text-right">
                                      Amount
                                    </th>
                                  </tr>
                                </thead>
                                <tbody className="divide-y divide-border/40">
                                  {filteredBankTxns.map((t) => (
                                    <tr
                                      key={t.id}
                                      className="hover:bg-surface"
                                    >
                                      <td className="px-4 py-2.5 tabular-nums text-muted">
                                        {t.date}
                                      </td>
                                      <td className="max-w-[200px] truncate px-4 py-2.5 text-foreground">
                                        {t.merchant_name ?? t.name}
                                      </td>
                                      <td className="px-4 py-2.5 capitalize text-muted">
                                        {t.category ?? "—"}
                                      </td>
                                      <td className="px-4 py-2.5">
                                        {t.pending ? (
                                          <span className="rounded-full bg-surface-muted px-2 py-0.5 text-[10px] text-muted">
                                            Pending
                                          </span>
                                        ) : (
                                          <span className="rounded-full bg-surface-muted px-2 py-0.5 text-[10px] text-muted">
                                            Posted
                                          </span>
                                        )}
                                      </td>
                                      <td className="px-4 py-2.5 text-right">
                                        <Money raw={t.amount} />
                                      </td>
                                    </tr>
                                  ))}
                                </tbody>
                              </table>
                            </div>
                            <p className="px-4 py-2 text-[11px] text-muted">
                              Showing {filteredBankTxns.length} most recent
                            </p>
                          </>
                        )}
                      </>
                    )}
                  </div>
                </div>

                {/* ── INSPECTOR (split at ≥1280px) ──────────────────────── */}
                {inspectorHolding != null && isWide && (
                  <HoldingInspector
                    holding={inspectorHolding}
                    token={token}
                    tradesCache={tradesCache}
                    setTradesCache={setTradesCache}
                    onClose={() => {
                      setSelectedSecurityKey(null);
                      setInspectorOpen(false);
                    }}
                    slideOver={false}
                  />
                )}
              </div>
            )}
          </section>
        </div>
      )}

      {/* ── INSPECTOR slide-over (below 1280px) ───────────────────────────── */}
      {inspectorHolding != null && !isWide && inspectorOpen && (
        <HoldingInspector
          holding={inspectorHolding}
          token={token}
          tradesCache={tradesCache}
          setTradesCache={setTradesCache}
          onClose={() => {
            setSelectedSecurityKey(null);
            setInspectorOpen(false);
          }}
          slideOver={true}
        />
      )}
    </div>
  );
}

// ── HoldingInspector ────────────────────────────────────────────────────────

function HoldingInspector({
  holding,
  token,
  tradesCache,
  setTradesCache,
  onClose,
  slideOver,
}: {
  holding: Holding;
  token: string;
  tradesCache: Map<string, InvestmentTransaction[]>;
  setTradesCache: Dispatch<SetStateAction<Map<string, InvestmentTransaction[]>>>;
  onClose: () => void;
  slideOver: boolean;
}) {
  const [inspectorTab, setInspectorTab] = useState<"lots" | "trades">("lots");
  const [tradesLoading, setTradesLoading] = useState(false);
  const [tradesError, setTradesError] = useState<string | null>(null);

  const securityKey = holding.security_id ?? null;
  const hasLots = holding.lots != null && holding.lots.length > 0;
  const hasTrades = securityKey != null;
  const trades =
    securityKey != null ? (tradesCache.get(securityKey) ?? null) : null;

  const showAcquired = hasLots
    ? holding.lots!.some((l) => l.acquired_date != null)
    : false;

  useEffect(() => {
    if (inspectorTab !== "trades" || !hasTrades || trades != null) return;
    if (securityKey == null) return;
    let active = true;
    void (async () => {
      setTradesLoading(true);
      setTradesError(null);
      try {
        const data = await listHoldingTransactions(securityKey, token);
        if (active) {
          setTradesCache((prev) => new Map(prev).set(securityKey, data));
        }
      } catch (err) {
        if (active) {
          setTradesError(
            err instanceof Error ? err.message : "Failed to load trades.",
          );
        }
      } finally {
        if (active) setTradesLoading(false);
      }
    })();
    return () => {
      active = false;
    };
  }, [inspectorTab, hasTrades, securityKey, trades, token, setTradesCache]);

  const gainLoss =
    holding.value != null && holding.cost_basis != null
      ? Number(holding.value) - Number(holding.cost_basis)
      : null;
  const gainPct =
    gainLoss !== null &&
    holding.cost_basis != null &&
    Number(holding.cost_basis) !== 0
      ? (gainLoss / Number(holding.cost_basis)) * 100
      : null;

  const content = (
    <div
      className={[
        "flex flex-col bg-surface",
        slideOver
          ? "fixed inset-y-0 right-0 z-30 w-80 border-l border-border shadow-xl"
          : "w-80 shrink-0 border-l border-border",
      ].join(" ")}
    >
      {/* Inspector header */}
      <div className="flex items-center justify-between border-b border-border px-4 py-3">
        <div className="min-w-0">
          <p className="truncate text-sm font-semibold text-foreground">
            {holding.ticker ?? holding.security_name}
          </p>
          {holding.ticker && holding.ticker !== holding.security_name && (
            <p className="truncate text-xs text-muted">
              {holding.security_name}
            </p>
          )}
        </div>
        <button
          type="button"
          onClick={onClose}
          className="ml-2 shrink-0 rounded p-1 text-muted transition hover:bg-surface-muted hover:text-foreground"
          aria-label="Close inspector"
        >
          ✕
        </button>
      </div>

      {/* Inspector summary */}
      <div className="border-b border-border px-4 py-3">
        <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
          <span className="text-muted">Qty</span>
          <span className="text-right tabular-nums text-foreground">
            {Number(holding.quantity).toFixed(
              Number(holding.quantity) % 1 === 0 ? 0 : 3,
            )}
          </span>
          <span className="text-muted">Price</span>
          <span className="text-right tabular-nums text-foreground">
            {holding.price != null ? USD.format(Number(holding.price)) : "—"}
          </span>
          <span className="text-muted">Value</span>
          <span className="text-right tabular-nums text-foreground">
            {holding.value != null ? USD.format(Number(holding.value)) : "—"}
          </span>
          <span className="text-muted">Cost Basis</span>
          <span className="text-right tabular-nums text-muted">
            {holding.cost_basis != null
              ? USD.format(Number(holding.cost_basis))
              : "—"}
          </span>
          <span className="text-muted">Gain/Loss</span>
          <span className="text-right">
            <GainLoss dollars={gainLoss} pct={gainPct} />
          </span>
        </div>
      </div>

      {/* Inspector tabs */}
      <div
        role="tablist"
        className="flex gap-1 border-b border-border px-4 py-2"
        onKeyDown={(e) => {
          const tabs = (["lots", "trades"] as const).filter(
            (t) => t !== "trades" || hasTrades,
          );
          const idx = tabs.indexOf(inspectorTab);
          if (e.key === "ArrowRight" && idx < tabs.length - 1)
            setInspectorTab(tabs[idx + 1]);
          if (e.key === "ArrowLeft" && idx > 0)
            setInspectorTab(tabs[idx - 1]);
        }}
      >
        {hasLots && (
          <button
            role="tab"
            aria-selected={inspectorTab === "lots"}
            type="button"
            onClick={() => setInspectorTab("lots")}
            className={[
              "rounded-md px-3 py-1 text-xs font-medium transition",
              inspectorTab === "lots"
                ? "bg-accent-soft text-accent"
                : "text-muted hover:bg-surface-muted hover:text-foreground",
            ].join(" ")}
          >
            Lots ({holding.lots!.length})
          </button>
        )}
        <button
          role="tab"
          aria-selected={inspectorTab === "trades"}
          type="button"
          onClick={() => setInspectorTab("trades")}
          disabled={!hasTrades}
          className={[
            "rounded-md px-3 py-1 text-xs font-medium transition",
            inspectorTab === "trades"
              ? "bg-accent-soft text-accent"
              : "text-muted hover:bg-surface-muted hover:text-foreground",
            !hasTrades ? "cursor-not-allowed opacity-40" : "",
          ].join(" ")}
        >
          Trades
        </button>
      </div>

      {/* Inspector content */}
      <div
        role="tabpanel"
        className="pragya-scroll min-h-0 flex-1 overflow-y-auto"
      >
        {inspectorTab === "lots" && (
          <>
            {!hasLots ? (
              <p className="p-4 text-center text-xs text-muted">
                No lot detail reported.
              </p>
            ) : (
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-border bg-surface-muted/60 text-[10px] uppercase tracking-wider text-muted">
                    <th className="px-4 py-1.5 text-right">Qty</th>
                    <th className="px-4 py-1.5 text-right">Cost</th>
                    {showAcquired && (
                      <th className="px-4 py-1.5 text-left">Acquired</th>
                    )}
                  </tr>
                </thead>
                <tbody className="divide-y divide-border/40">
                  {holding.lots!.map((lot, i) => (
                    <tr key={i} className="hover:bg-surface">
                      <td className="px-4 py-1.5 text-right tabular-nums text-foreground">
                        {lot.quantity}
                      </td>
                      <td className="px-4 py-1.5 text-right tabular-nums text-muted">
                        {lot.cost_basis != null
                          ? USD.format(Number(lot.cost_basis))
                          : "—"}
                      </td>
                      {showAcquired && (
                        <td className="px-4 py-1.5 text-muted">
                          {lot.acquired_date ?? "—"}
                        </td>
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </>
        )}

        {inspectorTab === "trades" && (
          <>
            {tradesLoading ? (
              <div className="space-y-2 p-4">
                {[1, 2, 3].map((i) => (
                  <div
                    key={i}
                    className="h-6 animate-pulse rounded bg-border"
                  />
                ))}
              </div>
            ) : tradesError ? (
              <p className="p-4 text-xs text-danger">{tradesError}</p>
            ) : trades == null || trades.length === 0 ? (
              <p className="p-4 text-center text-xs text-muted">
                No trades found for this security.
              </p>
            ) : (
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-border bg-surface-muted/60 text-[10px] uppercase tracking-wider text-muted">
                    <th className="px-4 py-1.5 text-left">Date</th>
                    <th className="px-4 py-1.5 text-left">Action</th>
                    <th className="px-4 py-1.5 text-right">Qty</th>
                    <th className="px-4 py-1.5 text-right">Amount</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border/40">
                  {trades.map((t) => (
                    <tr key={t.id} className="hover:bg-surface">
                      <td className="px-4 py-1.5 tabular-nums text-muted">
                        {t.date}
                      </td>
                      <td className="px-4 py-1.5 capitalize text-foreground">
                        {t.subtype ?? t.type}
                      </td>
                      <td className="px-4 py-1.5 text-right tabular-nums text-foreground">
                        {t.quantity}
                      </td>
                      <td className="px-4 py-1.5 text-right">
                        <Money raw={t.amount} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </>
        )}
      </div>
    </div>
  );

  if (slideOver) {
    return (
      <div role="dialog" aria-modal="true" aria-label="Holding inspector">
        {/* Backdrop */}
        <div className="fixed inset-0 z-20 bg-black/20" onClick={onClose} />
        {content}
      </div>
    );
  }

  return content;
}
