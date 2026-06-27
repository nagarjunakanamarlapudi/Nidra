import { describe, expect, it, vi } from "vitest";
import { disconnectInstitution, listAccounts, listHoldings, syncFinance } from "@/lib/api";

describe("listAccounts", () => {
  it("sends bearer token and returns accounts", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true, json: async () => [{ account_id: 3, item_id: 7, institution: "Chase", institution_logo: null, institution_color: "#095aa6", name: "Checking", official_name: "CHECKING ACCOUNT", mask: "1234", type: "depository", subtype: "checking", current_balance: "500", iso_currency: "USD" }],
    });
    vi.stubGlobal("fetch", fetchMock);
    const accounts = await listAccounts("tok", "http://api");
    expect(accounts[0].account_id).toBe(3);
    expect(accounts[0].item_id).toBe(7);
    expect(accounts[0].name).toBe("Checking");
    expect(accounts[0].official_name).toBe("CHECKING ACCOUNT");
    expect(accounts[0].mask).toBe("1234");
    expect(accounts[0].institution_color).toBe("#095aa6");
    expect(fetchMock).toHaveBeenCalledWith(
      "http://api/finance/accounts",
      expect.objectContaining({ headers: expect.objectContaining({ Authorization: "Bearer tok" }) }),
    );
    vi.unstubAllGlobals();
  });
});

describe("syncFinance", () => {
  it("POSTs /finance/sync with bearer token", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ ok: true }),
    });
    vi.stubGlobal("fetch", fetchMock);
    await syncFinance("tok", "http://api");
    expect(fetchMock).toHaveBeenCalledWith(
      "http://api/finance/sync",
      expect.objectContaining({
        method: "POST",
        headers: expect.objectContaining({ Authorization: "Bearer tok" }),
      }),
    );
    vi.unstubAllGlobals();
  });
});

describe("disconnectInstitution", () => {
  it("sends DELETE /finance/items/{itemId} with bearer token", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ removed: true }),
    });
    vi.stubGlobal("fetch", fetchMock);
    await disconnectInstitution(42, "tok", "http://api");
    expect(fetchMock).toHaveBeenCalledWith(
      "http://api/finance/items/42",
      expect.objectContaining({
        method: "DELETE",
        headers: expect.objectContaining({ Authorization: "Bearer tok" }),
      }),
    );
    vi.unstubAllGlobals();
  });
});

describe("listHoldings", () => {
  it("GETs /finance/holdings with bearer token and returns holdings", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => [
        {
          account_id: 5,
          ticker: "AAPL",
          security_name: "Apple Inc.",
          quantity: "10",
          price: "185.50",
          value: "1855.00",
          iso_currency: "USD",
          cost_basis: "1000.00",
          lots: null,
        },
      ],
    });
    vi.stubGlobal("fetch", fetchMock);
    const holdings = await listHoldings("tok", "http://api");
    expect(holdings).toHaveLength(1);
    expect(holdings[0].account_id).toBe(5);
    expect(holdings[0].ticker).toBe("AAPL");
    expect(holdings[0].value).toBe("1855.00");
    expect(holdings[0].cost_basis).toBe("1000.00");
    expect(fetchMock).toHaveBeenCalledWith(
      "http://api/finance/holdings",
      expect.objectContaining({
        headers: expect.objectContaining({ Authorization: "Bearer tok" }),
      }),
    );
    vi.unstubAllGlobals();
  });
});
