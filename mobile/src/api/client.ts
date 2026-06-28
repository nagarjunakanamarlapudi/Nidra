// Real backend client — talks to the deployed Nidra/Pragya API (the same one the
// web app + extension use). This is the first wire-up past the mock seam: the
// Talk sheet posts to /chat and renders the live reply.
//
// Config comes from Expo public env vars (EXPO_PUBLIC_*), read from `mobile/.env`
// (gitignored — copy `.env.example` and fill it in). The single-user bearer token
// is NEVER committed. For production, move it to expo-secure-store behind a sign-in
// screen (mirror the web's TokenGate). API_BASE keeps a safe public default.

export const API_BASE = process.env.EXPO_PUBLIC_API_BASE ?? 'https://api.134-199-180-135.sslip.io';
const API_TOKEN = process.env.EXPO_PUBLIC_API_TOKEN ?? '';

const authHeaders = (): Record<string, string> => ({
  'Content-Type': 'application/json',
  Authorization: `Bearer ${API_TOKEN}`,
});

export interface ChatReply {
  reply: string;
  conversationId: number | null;
}

// POST /chat → { reply, conversation_id }. Pass the prior conversationId to keep
// the thread; null starts a new conversation (the backend creates one).
export async function sendChat(
  message: string,
  conversationId: number | null,
): Promise<ChatReply> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}/chat`, {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify({ message, conversation_id: conversationId }),
    });
  } catch {
    throw new Error("Can't reach Nidra — check your connection.");
  }
  if (res.status === 401) throw new Error('Unauthorized — the access token is wrong.');
  if (!res.ok) throw new Error(`Nidra had trouble (${res.status}). Try again.`);
  const data = (await res.json()) as { reply: string; conversation_id: number | null };
  return { reply: data.reply, conversationId: data.conversation_id ?? conversationId };
}
