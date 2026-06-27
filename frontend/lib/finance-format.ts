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
