import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  deleteConnector,
  disableConnector,
  disconnectConnectorAccount,
  enableConnectorSecret,
  listConnectors,
  startConnectorOAuth,
  syncConnector,
  testConnector,
} from "@/lib/api";

function mockResponse(status: number, jsonBody: unknown): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => jsonBody,
  } as Response;
}

const BASE = "https://api.example.com";

describe("connectors api", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("listConnectors GETs with the auth header", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockResolvedValue(mockResponse(200, [{ key: "google_calendar" }]));
    const res = await listConnectors("tok", BASE);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(`${BASE}/connectors`);
    expect((init?.headers as Record<string, string>)["Authorization"]).toBe("Bearer tok");
    expect(res[0].key).toBe("google_calendar");
  });

  it("enableConnectorSecret POSTs a wrapped config body", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockResolvedValue(mockResponse(200, { key: "x", status: "connected" }));
    await enableConnectorSecret("x", { api_key: "K" }, "tok", BASE);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(`${BASE}/connectors/x/enable`);
    expect(init?.method).toBe("POST");
    expect(JSON.parse(init?.body as string)).toEqual({ config: { api_key: "K" } });
  });

  it("startConnectorOAuth returns the authorize URL", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockResolvedValue(
      mockResponse(200, { authorize_url: "https://accounts.google.com/o/oauth2/v2/auth?x=1" }),
    );
    const url = await startConnectorOAuth("google_calendar", { client_id: "c" }, "tok", BASE);
    expect(url).toBe("https://accounts.google.com/o/oauth2/v2/auth?x=1");
  });

  it("syncConnector POSTs and returns the count", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockResolvedValue(mockResponse(200, { items: 5 }));
    const r = await syncConnector("x", "tok", BASE);
    expect(r.items).toBe(5);
    expect(fetchMock.mock.calls[0][1]?.method).toBe("POST");
  });

  it("testConnector reports health", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockResolvedValue(mockResponse(200, { ok: true, detail: "fine" }));
    expect((await testConnector("x", "tok", BASE)).ok).toBe(true);
  });

  it("disableConnector POSTs to /disable", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockResolvedValue(mockResponse(200, { key: "x", enabled: false }));
    await disableConnector("x", "tok", BASE);
    expect(fetchMock.mock.calls[0][0]).toBe(`${BASE}/connectors/x/disable`);
  });

  it("deleteConnector issues a DELETE", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockResolvedValue(mockResponse(200, { removed: true }));
    await deleteConnector("x", "tok", BASE);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(`${BASE}/connectors/x`);
    expect(init?.method).toBe("DELETE");
  });

  it("disconnectConnectorAccount DELETEs the account path and returns the detail", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockResolvedValue(mockResponse(200, { key: "google_calendar", accounts: [] }));
    const res = await disconnectConnectorAccount("google_calendar", 7, "tok", BASE);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(`${BASE}/connectors/google_calendar/accounts/7`);
    expect(init?.method).toBe("DELETE");
    expect((init?.headers as Record<string, string>)["Authorization"]).toBe("Bearer tok");
    expect(res.accounts).toEqual([]);
  });

  it("surfaces a friendly 401", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockResolvedValue(mockResponse(401, {}));
    await expect(listConnectors("bad", BASE)).rejects.toThrow(/Unauthorized/);
  });
});
