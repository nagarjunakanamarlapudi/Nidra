# Finance Master/Detail/Inspector Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Finance page's accordion layout with a master/detail/inspector three-panel design featuring a sticky header, account rail, detail panel, and an inspector that splits at ≥1280px.

**Architecture:** Two files — `finance-format.ts` (pure utility functions with no React dependency) and the rewritten `Finance.tsx` ("use client" component with all Plaid wiring and layout). The util file is imported by Finance.tsx, separating concerns cleanly. No new dependencies are introduced.

**Tech Stack:** Next.js 16.2.9 (non-standard), React 19, Tailwind CSS v4 (utility-first), TypeScript 5 strict mode, Vitest (tests only touch api.ts), react-plaid-link.

## Global Constraints

- Next.js version is 16.2.9 — non-standard; check `node_modules/next/dist/docs/` before adding any Next.js-specific API
- No `useSearchParams`, no `useRouter` — must work as a pure "use client" component with no router state
- No virtualization libraries — not in package.json
- Do NOT modify `api.ts`
- The git repo root is `/Users/nagarjuna/projects/naga_personal_assistant` (NOT the frontend directory)
- Do NOT push to remote
- All Tailwind classes must use CSS variable tokens defined in `globals.css` (bg-background, bg-surface, bg-surface-muted, text-foreground, text-muted, border-border, text-accent, bg-accent, text-danger, bg-danger)
- `min-w-0` on flex children and `min-h-0` on flex parents are required for proper layout
- The exported component signature must be exactly: `export function Finance({ token }: { token: string })`
- Existing tests in `__tests__/api.finance.test.ts` must continue to pass unchanged

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `frontend/lib/finance-format.ts` | Create | Pure format/compute helpers: USD formatter, formatBalance, isDebt, computeNetWorth, groupByItemId |
| `frontend/app/Finance.tsx` | Rewrite | Full master/detail/inspector component: all state, layout, sub-components, Plaid wiring |
| `frontend/__tests__/api.finance.test.ts` | No change | Existing tests must pass |

---

### Task 1: Create `finance-format.ts`

**Files:**
- Create: `frontend/lib/finance-format.ts`

**Interfaces:**
- Consumes: `FinanceAccount` type from `./api`
- Produces:
  - `USD: Intl.NumberFormat`
  - `formatBalance(balance: string | null | undefined, currency: string | null): string`
  - `isDebt(type: string): boolean`
  - `computeNetWorth(accounts: FinanceAccount[]): number`
  - `groupByItemId(accounts: FinanceAccount[]): [number, FinanceAccount[]][]`

- [ ] **Step 1: Write `finance-format.ts`**

```typescript
import type { FinanceAccount } from "./api";

export const USD = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  minimumFractionDigits: 2,
});

export function formatBalance(
  balance: string | null | undefined,
  currency: string | null,
): string {
  if (balance == null) return "—";
  const n = Number(balance);
  if (isNaN(n)) return "—";
  const sym = (currency ?? "USD").toUpperCase();
  if (sym === "USD") return USD.format(n);
  return `${n.toFixed(2)} ${sym}`;
}

const CREDIT_TYPES = new Set(["credit", "loan"]);

export function isDebt(type: string): boolean {
  return CREDIT_TYPES.has(type.toLowerCase());
}

export function computeNetWorth(accounts: FinanceAccount[]): number {
  return accounts.reduce((sum, a) => {
    const n = Number(a.current_balance ?? 0);
    if (isNaN(n)) return sum;
    return isDebt(a.type) ? sum - n : sum + n;
  }, 0);
}

export function groupByItemId(
  accounts: FinanceAccount[],
): [number, FinanceAccount[]][] {
  const map = new Map<number, FinanceAccount[]>();
  for (const a of accounts) {
    if (!map.has(a.item_id)) map.set(a.item_id, []);
    map.get(a.item_id)!.push(a);
  }
  return Array.from(map.entries());
}
```

- [ ] **Step 2: Run lint and type-check**

```bash
cd /Users/nagarjuna/projects/naga_personal_assistant/frontend && npm run lint && npm run build -- --dry-run 2>&1 | head -40
```

Expected: No errors from the new file.

- [ ] **Step 3: Run tests to confirm no regressions**

```bash
cd /Users/nagarjuna/projects/naga_personal_assistant/frontend && npm test
```

Expected: All tests pass (the format util is not tested in isolation — it will be exercised through Finance.tsx).

---

### Task 2: Rewrite `Finance.tsx` — inline sub-components

**Files:**
- Modify: `frontend/app/Finance.tsx` (full rewrite)

**Interfaces:**
- Consumes: All from `../lib/api` (already imported), all from `../lib/finance-format`
- Produces: `export function Finance({ token }: { token: string })`

This task writes the complete new `Finance.tsx` implementing the master/detail/inspector layout with all sub-components, state, effects, and Plaid wiring.

**Design decisions baked in:**
- `AccountRail` is JSX inline in Finance (not a separate file) — it needs direct access to `selectedAccountId`, `railFilter`, etc.
- `HoldingsTable` is a named inner function that receives props — compact mode when `selectedSecurityKey != null`
- `HoldingInspector` is a named inner function that renders as flex aside (≥1280px) or fixed slide-over (<1280px)
- `TradesTable`, `LotsTable`, `ActivityTable`, `TransactionsTable` are named inner functions

- [ ] **Step 1: Write the complete `Finance.tsx`**

The full file must contain, in order:

1. `"use client"` directive
2. Imports (React hooks, usePlaidLink, all api types and functions, all finance-format exports)
3. Inline sub-components (no export): `InstitutionBadge`, `TypeChip`, `StatusDot`, `Money`, `GainLoss`
4. Helper function: `computeDefaultAccountId`
5. Main `Finance` component with all state declarations
6. `useEffect` for viewport tracking (≥1280px → `isWide`)
7. `useEffect` for initial data load (accounts + holdings + link token)
8. `useCallback refresh` function
9. `useCallback onPlaidSuccess`
10. `usePlaidLink` hook call
11. `handleConnect`, `handleSync`, `handleDisconnect` functions
12. Derived values: `netWorth`, `totalAssets`, `totalDebts`, `institutionGroups`, `selectedAccount`, `accountHoldings`, `isInvestment`, etc.
13. `useEffect` for default selection (fires when accounts + holdings first load)
14. `useEffect` for lazy-loading transactions when `selectedAccountId` changes
15. `useEffect` for Esc key to close inspector
16. Inner components (defined inside Finance function body for closure access):
    - `RailRow` (a single account row in the left rail)
    - `HoldingsTable` (sortable table with compact mode)
    - `LotsTable` (from holding.lots)
    - `TradesTable` (lazy loaded, cached in tradesCache)
    - `HoldingInspector` (flex aside or slide-over)
    - `ActivityTable` (investment transactions)
    - `TransactionsTable` (bank/credit transactions)
17. Return JSX: header + body (rail + detail panel)

The complete file content (write exactly):

```tsx
"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { usePlaidLink } from "react-plaid-link";
import {
  createLinkToken,
  disconnectInstitution,
  exchangePublicToken,
  listAccountTransactions,
  listAccounts,
  listHoldings,
  listHoldingTransactions,
  listInvestmentTransactions,
  syncFinance,
  type BankTransaction,
  type FinanceAccount,
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

  const [isWide, setIsWide] = useState(false);

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
    setIsWide(mq.matches);
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
    const isInvestment = selectedAccount.type === "investment";

    setDetailLoading(true);
    setDetailError(null);
    let active = true;
    void (async () => {
      try {
        let data: BankTransaction[] | InvestmentTransaction[];
        if (isInvestment) {
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

  const selectedAccount = accounts.find(
    (a) => a.account_id === selectedAccountId,
  ) ?? null;
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
        .map(([itemId, accs]) => [
          itemId,
          accs.filter(
            (a) =>
              (a.official_name ?? a.name)
                .toLowerCase()
                .includes(railFilter.toLowerCase()) ||
              a.institution.toLowerCase().includes(railFilter.toLowerCase()),
          ),
        ] as [number, FinanceAccount[]])
        .filter(([, accs]) => accs.length > 0)
    : institutionGroups;

  // Holdings sort + filter
  const filteredHoldings = holdingsFilter.trim()
    ? accountHoldings.filter(
        (h) =>
          (h.ticker ?? "").toLowerCase().includes(holdingsFilter.toLowerCase()) ||
          h.security_name.toLowerCase().includes(holdingsFilter.toLowerCase()),
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

  function ariaSortFor(col: typeof sortCol): "ascending" | "descending" | "none" {
    if (sortCol !== col) return "none";
    return sortDir === "asc" ? "ascending" : "descending";
  }

  // Txn data from cache
  const rawTxns = selectedAccountId != null ? txnCache.get(selectedAccountId) ?? null : null;
  const bankTxns: BankTransaction[] | null =
    !isInvestment && rawTxns != null
      ? (rawTxns as BankTransaction[])
      : null;
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
      ? investTxns.filter(
          (t) =>
            (t.ticker ?? t.name)
              .toLowerCase()
              .includes(txnFilter.toLowerCase()),
        )
      : investTxns
    : null;

  // Inspector holding
  const inspectorHolding =
    selectedSecurityKey != null
      ? accountHoldings.find(
          (h) =>
            h.security_id === selectedSecurityKey ||
            h.security_name === selectedSecurityKey,
        ) ?? null
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
              <span
                className={`font-serif text-3xl tabular-nums tracking-tight ${netWorth < 0 ? "text-danger" : "text-foreground"}`}
              >
                {USD.format(netWorth)}
              </span>
              <span className="text-xs text-muted">
                Assets {USD.format(totalAssets)} · Debts {USD.format(totalDebts)}
              </span>
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
                  e.currentTarget.querySelectorAll<HTMLElement>('[role="option"]'),
                );
                const idx = opts.findIndex(
                  (el) => el.dataset.accountId === String(selectedAccountId),
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
                          onClick={() => handleDisconnect(itemId, institutionName).catch(() => {})}
                          className="shrink-0 text-[10px] text-muted transition hover:text-danger"
                          disabled={disconnecting != null}
                        >
                          Disconnect
                        </button>
                      ) : (
                        <span className="text-[10px] text-muted">Removing…</span>
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
                          <span
                            className={[
                              "shrink-0 text-xs tabular-nums",
                              debt
                                ? balance > 0
                                  ? "text-danger"
                                  : "text-muted"
                                : balance < 0
                                  ? "text-danger"
                                  : "text-foreground",
                            ].join(" ")}
                          >
                            {formatBalance(a.current_balance, a.iso_currency)}
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
                          {selectedAccount.official_name ?? selectedAccount.name}
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
                        {isInvestment && accountHoldings.length > 0 && (
                          <p className="text-xs text-muted">
                            <GainLoss
                              dollars={holdingsWithCostBasis.length > 0 ? totalGain : null}
                              pct={
                                holdingsWithCostBasis.length > 0 && totalCost !== 0
                                  ? (totalGain / totalCost) * 100
                                  : null
                              }
                            />
                            {hasPartialCostBasis && (
                              <span className="ml-1 text-muted">(partial)</span>
                            )}
                          </p>
                        )}
                      </div>
                    </div>

                    {/* Tab bar (only for investment accounts with multiple tabs) */}
                    {isInvestment && (
                      <div
                        role="tablist"
                        className="mt-3 flex gap-1"
                        onKeyDown={(e) => {
                          const tabs: typeof activeTab[] = [
                            "holdings",
                            "activity",
                          ];
                          const idx = tabs.indexOf(activeTab as "holdings" | "activity");
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
                          ]
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
                            onChange={(e) => setHoldingsFilter(e.target.value)}
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
                                          e.currentTarget.closest("tbody")
                                            ?.querySelectorAll<HTMLElement>("tr") ?? [];
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
                                      </td>
                                      {!selectedSecurityKey && (
                                        <td className="px-4 py-2.5 text-right tabular-nums text-muted">
                                          {h.cost_basis != null
                                            ? USD.format(Number(h.cost_basis))
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

                {/* ── INSPECTOR (split at ≥1280px, slide-over below) ─────── */}
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
  setTradesCache: React.Dispatch<
    React.SetStateAction<Map<string, InvestmentTransaction[]>>
  >;
  onClose: () => void;
  slideOver: boolean;
}) {
  const [inspectorTab, setInspectorTab] = useState<"lots" | "trades">("lots");
  const [tradesLoading, setTradesLoading] = useState(false);
  const [tradesError, setTradesError] = useState<string | null>(null);

  const securityKey = holding.security_id ?? null;
  const hasLots = holding.lots != null && holding.lots.length > 0;
  const hasTrades = securityKey != null;
  const trades = securityKey != null ? tradesCache.get(securityKey) ?? null : null;

  const showAcquired = hasLots
    ? holding.lots!.some((l) => l.acquired_date != null)
    : false;

  useEffect(() => {
    if (inspectorTab !== "trades" || !hasTrades || trades != null) return;
    if (securityKey == null) return;
    setTradesLoading(true);
    setTradesError(null);
    let active = true;
    void (async () => {
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
            <p className="truncate text-xs text-muted">{holding.security_name}</p>
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
          const tabs: ("lots" | "trades")[] = ["lots", "trades"].filter(
            (t) => t !== "trades" || hasTrades,
          ) as ("lots" | "trades")[];
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
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Holding inspector"
      >
        {/* Backdrop */}
        <div
          className="fixed inset-0 z-20 bg-black/20"
          onClick={onClose}
        />
        {content}
      </div>
    );
  }

  return content;
}
```

- [ ] **Step 2: Run lint**

```bash
cd /Users/nagarjuna/projects/naga_personal_assistant/frontend && npm run lint 2>&1
```

Expected: zero errors. Fix any TypeScript or ESLint errors before proceeding.

- [ ] **Step 3: Run tests**

```bash
cd /Users/nagarjuna/projects/naga_personal_assistant/frontend && npm test 2>&1
```

Expected: all 5 tests pass (listAccounts, syncFinance, disconnectInstitution, listHoldings + one more from api.test.ts).

- [ ] **Step 4: Run build**

```bash
cd /Users/nagarjuna/projects/naga_personal_assistant/frontend && npm run build 2>&1
```

Expected: successful build with no type errors.

- [ ] **Step 5: Fix any TypeScript/lint errors**

If lint or build failed, analyze the errors and fix them. Common issues to look for:
- `React.Dispatch` import — needs `import React from "react"` or use `import { Dispatch } from "react"`
- Stale `lastSynced` variable unused warning
- `listHoldingTransactions` being called in HoldingInspector which is outside Finance closure — token must be passed as prop
- `tradesCache`/`setTradesCache` must be passed as props to HoldingInspector since it's defined outside Finance

---

### Task 3: Commit

**Files:** All changed files

- [ ] **Step 1: Stage files**

```bash
cd /Users/nagarjuna/projects/naga_personal_assistant && git add frontend/lib/finance-format.ts frontend/app/Finance.tsx
```

- [ ] **Step 2: Commit**

```bash
cd /Users/nagarjuna/projects/naga_personal_assistant && git commit -m "$(cat <<'EOF'
feat(finance): master/detail/inspector redesign (UX panel synthesis)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 3: Write report**

Write to `/Users/nagarjuna/projects/naga_personal_assistant/.superpowers/sdd/finance-redesign-report.md`.

---

## Self-Review

### Spec coverage check

| Requirement | Task |
|---|---|
| finance-format.ts with USD, formatBalance, isDebt, computeNetWorth, groupByItemId | Task 1 |
| Sticky header with net worth, assets/debts, sync+connect buttons | Task 2 |
| Account rail (left, 300px) with institution badge, filter, selectable rows | Task 2 |
| Detail panel with account header + tab bar | Task 2 |
| Inspector as flex aside ≥1280px / slide-over below 1280px | Task 2 |
| InstitutionBadge component | Task 2 |
| TypeChip component | Task 2 |
| Money component with sign convention | Task 2 |
| GainLoss component | Task 2 |
| All state variables | Task 2 |
| Default selection logic with localStorage | Task 2 |
| Viewport tracking for isWide | Task 2 |
| Holdings table with sort cols | Task 2 |
| Holdings compact mode when inspector open | Task 2 |
| Activity table | Task 2 |
| Transactions table (bank/credit) | Task 2 |
| Lots table with conditional ACQUIRED column | Task 2 |
| Trades table with lazy loading + cache | Task 2 |
| Caching for txnCache + tradesCache | Task 2 |
| Cache cleared on sync | Task 2 |
| localStorage for account selection | Task 2 |
| Selection change resets filters/sort/inspector | Task 2 |
| Sign convention: amount<0→green, amount>0→danger | Task 2 |
| All-time gain "(partial)" when cost_basis missing for some | Task 2 |
| Empty states (all cases) | Task 2 |
| Loading skeletons | Task 2 |
| Error banner + inline errors | Task 2 |
| Plaid wiring (same as original) | Task 2 |
| Keyboard: ↑/↓ rail, Enter/Space select, ↑/↓ holdings, Enter open inspector | Task 2 |
| Keyboard: ←/→ inspector tabs, Esc close inspector, / focus filter | Task 2 |
| Accessibility: aria-sort, aria-selected, role="dialog"/aria-modal, role="listbox"/role="option" | Task 2 |
| Disconnect button per institution | Task 2 |
| "Showing N most recent" footer | Task 2 |

### Placeholder scan

No TODOs, TBDs, or incomplete steps found.

### Type consistency check

- `HoldingInspector` receives `tradesCache: Map<string, InvestmentTransaction[]>` and `setTradesCache: React.Dispatch<React.SetStateAction<Map<string, InvestmentTransaction[]>>>` — matches Finance state declarations
- `token: string` is passed as prop to HoldingInspector — allows `listHoldingTransactions` call
- `gainLoss: number | null` and `pct: number | null` match GainLoss props
- `raw: string | null` matches Money props
- `sortCol` type is `"ticker" | "qty" | "price" | "value" | "gain"` — matches all toggle/sort usages

### Issues to fix before implementation

1. `React.Dispatch` — HoldingInspector uses `React.Dispatch<React.SetStateAction<...>>` — need to either import `React` as default or use `import { Dispatch, SetStateAction } from "react"`. The plan uses `React.Dispatch` inline in the prop type, so need `import React from "react"` or restructure. **Fix:** Add `import { type Dispatch, type SetStateAction } from "react"` and use `Dispatch<SetStateAction<Map<...>>>`.

2. `txnFilterRef` — used for both `isInvestment + activity` and `!isInvestment` branches. Since both branches use `ref={txnFilterRef}`, this is fine (only one branch renders at a time).

3. `listHoldingTransactions` is imported at top of Finance.tsx, so it's accessible inside HoldingInspector defined in the same file.
