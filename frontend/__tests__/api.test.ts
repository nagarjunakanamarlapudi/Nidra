import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  getConversation,
  listConversations,
  listDigests,
  runDigest,
  sendChat,
} from "@/lib/api";

/** Build a minimal `Response`-like object for mocking `fetch`. */
function mockResponse(
  status: number,
  jsonBody: unknown,
): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => jsonBody,
  } as Response;
}

describe("sendChat", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("posts to the right URL with auth header and JSON body", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockResolvedValue(
      mockResponse(200, { reply: "hi there", conversation_id: 7 }),
    );

    await sendChat({
      message: "hello",
      conversationId: 7,
      token: "secret-token",
      apiBase: "https://api.example.com",
    });

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("https://api.example.com/chat");
    expect(init?.method).toBe("POST");

    const headers = init?.headers as Record<string, string>;
    expect(headers["Authorization"]).toBe("Bearer secret-token");
    expect(headers["Content-Type"]).toBe("application/json");

    expect(JSON.parse(init?.body as string)).toEqual({
      message: "hello",
      conversation_id: 7,
    });
  });

  it("omits conversation_id on the first turn", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockResolvedValue(
      mockResponse(200, { reply: "welcome", conversation_id: 1 }),
    );

    await sendChat({
      message: "first message",
      token: "secret-token",
      apiBase: "https://api.example.com",
    });

    const [, init] = fetchMock.mock.calls[0];
    expect(JSON.parse(init?.body as string)).toEqual({
      message: "first message",
    });
  });

  it("includes effort in the body when provided", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockResolvedValue(
      mockResponse(200, { reply: "ok", conversation_id: 1 }),
    );

    await sendChat({
      message: "hi",
      token: "secret-token",
      apiBase: "https://api.example.com",
      effort: "high",
    });

    const [, init] = fetchMock.mock.calls[0];
    expect(JSON.parse(init?.body as string)).toEqual({ message: "hi", effort: "high" });
  });

  it("maps conversation_id to conversationId in the result", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockResolvedValue(
      mockResponse(200, { reply: "mapped reply", conversation_id: 42 }),
    );

    const result = await sendChat({
      message: "hello",
      token: "secret-token",
      apiBase: "https://api.example.com",
    });

    expect(result).toEqual({ reply: "mapped reply", conversationId: 42 });
  });

  it("throws the unauthorized message on a 401", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockResolvedValue(mockResponse(401, { detail: "nope" }));

    await expect(
      sendChat({
        message: "hello",
        token: "bad-token",
        apiBase: "https://api.example.com",
      }),
    ).rejects.toThrow("Unauthorized: check your access token");
  });

  it("throws a descriptive error on other non-2xx responses", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockResolvedValue(
      mockResponse(500, { detail: "boom" }),
    );

    await expect(
      sendChat({
        message: "hello",
        token: "secret-token",
        apiBase: "https://api.example.com",
      }),
    ).rejects.toThrow("Chat request failed (500): boom");
  });
});

describe("listConversations", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("GETs /conversations with auth and maps created_at to createdAt", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockResolvedValue(
      mockResponse(200, [
        { id: 2, title: "second", created_at: "2026-06-20T10:00:00Z" },
        { id: 1, title: "first", created_at: "2026-06-19T10:00:00Z" },
      ]),
    );

    const result = await listConversations("tok", "https://api.example.com");

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("https://api.example.com/conversations");
    expect((init?.headers as Record<string, string>)["Authorization"]).toBe("Bearer tok");
    expect(result).toEqual([
      { id: 2, title: "second", createdAt: "2026-06-20T10:00:00Z" },
      { id: 1, title: "first", createdAt: "2026-06-19T10:00:00Z" },
    ]);
  });

  it("throws the unauthorized message on a 401", async () => {
    vi.mocked(fetch).mockResolvedValue(mockResponse(401, { detail: "no" }));
    await expect(listConversations("bad", "https://api.example.com")).rejects.toThrow(
      "Unauthorized: check your access token",
    );
  });
});

describe("getConversation", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("GETs /conversations/:id and returns its messages", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockResolvedValue(
      mockResponse(200, {
        id: 5,
        messages: [
          { role: "user", content: "hi" },
          { role: "assistant", content: "hello" },
        ],
      }),
    );

    const result = await getConversation(5, "tok", "https://api.example.com");

    expect(fetchMock.mock.calls[0][0]).toBe("https://api.example.com/conversations/5");
    expect(result).toEqual({
      id: 5,
      messages: [
        { role: "user", content: "hi" },
        { role: "assistant", content: "hello" },
      ],
    });
  });
});

describe("digests", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("listDigests GETs /digests and maps created_at", async () => {
    vi.mocked(fetch).mockResolvedValue(
      mockResponse(200, [
        { id: 2, content: "hi", delivered: "stored", created_at: "2026-06-20T08:00:00Z" },
      ]),
    );
    const result = await listDigests("tok", "https://api.example.com");
    expect(result).toEqual([
      { id: 2, content: "hi", delivered: "stored", createdAt: "2026-06-20T08:00:00Z" },
    ]);
  });

  it("runDigest POSTs /digests/run", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockResolvedValue(
      mockResponse(200, {
        id: 5,
        content: "your digest",
        delivered: "telegram",
        created_at: "2026-06-20T08:00:00Z",
      }),
    );

    const d = await runDigest("tok", "https://api.example.com");

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("https://api.example.com/digests/run");
    expect(init?.method).toBe("POST");
    expect(d.content).toBe("your digest");
    expect(d.delivered).toBe("telegram");
  });
});
