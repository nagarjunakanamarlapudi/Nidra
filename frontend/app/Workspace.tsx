"use client";

import { useCallback, useEffect, useState } from "react";
import { Chat, type DisplayMessage } from "@/app/Chat";
import { Connectors } from "@/app/Connectors";
import { Finance } from "@/app/Finance";
import { Sidebar } from "@/app/Sidebar";
import {
  getConversation,
  listConversations,
  listDigests,
  runDigest,
  sendChat,
  type ConversationSummary,
  type Digest,
  type Effort,
} from "@/lib/api";

type View = "chat" | "finance" | "connectors";

const VIEW_LABELS: Record<View, string> = {
  chat: "Chat",
  finance: "Finance",
  connectors: "Connectors",
};

interface WorkspaceProps {
  /** Access token used to authenticate requests. */
  token: string;
  /** Clear the token and return to the sign-in screen. */
  onSignOut: () => void;
}

function newId(): string {
  return Math.random().toString(36).slice(2);
}

/** Two-pane chat: the history sidebar + the active conversation. Owns the
 * conversation list, the selected conversation, and its messages. */
export function Workspace({ token, onSignOut }: WorkspaceProps) {
  const [view, setView] = useState<View>(() =>
    typeof window !== "undefined" && new URLSearchParams(window.location.search).get("status")
      ? "connectors"
      : "chat",
  );
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [currentId, setCurrentId] = useState<number | null>(null);
  const [messages, setMessages] = useState<DisplayMessage[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [digest, setDigest] = useState<Digest | null>(null);
  const [digestBusy, setDigestBusy] = useState(false);

  const refreshConversations = useCallback(async () => {
    try {
      setConversations(await listConversations(token));
    } catch {
      // Non-fatal: the sidebar just keeps its current contents.
    }
  }, [token]);

  useEffect(() => {
    let active = true;
    void (async () => {
      try {
        const [convos, digests] = await Promise.all([
          listConversations(token),
          listDigests(token),
        ]);
        if (active) {
          setConversations(convos);
          setDigest(digests[0] ?? null);
        }
      } catch {
        // Non-fatal: the sidebar / digest card just stay empty.
      }
    })();
    return () => {
      active = false;
    };
  }, [token]);

  const generateDigest = useCallback(async () => {
    setDigestBusy(true);
    try {
      setDigest(await runDigest(token));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not generate the digest.");
    } finally {
      setDigestBusy(false);
    }
  }, [token]);

  const selectConversation = useCallback(
    async (id: number) => {
      setError(null);
      try {
        const detail = await getConversation(id, token);
        setMessages(
          detail.messages.map((m) => ({ id: newId(), role: m.role, text: m.content })),
        );
        setCurrentId(id);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Could not load that conversation.");
      }
    },
    [token],
  );

  const newChat = useCallback(() => {
    setMessages([]);
    setCurrentId(null);
    setError(null);
  }, []);

  const send = useCallback(
    async (text: string, effort: Effort | undefined) => {
      const wasNew = currentId === null;
      setMessages((prev) => [...prev, { id: newId(), role: "user", text }]);
      setError(null);
      setLoading(true);
      try {
        const response = await sendChat({
          message: text,
          conversationId: currentId ?? undefined,
          token,
          effort,
        });
        setCurrentId(response.conversationId);
        setMessages((prev) => [
          ...prev,
          { id: newId(), role: "assistant", text: response.reply },
        ]);
        if (wasNew) {
          // A new conversation now exists — surface it in the sidebar.
          void refreshConversations();
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : "Something went wrong.");
      } finally {
        setLoading(false);
      }
    },
    [currentId, token, refreshConversations],
  );

  return (
    <main className="flex h-dvh">
      <Sidebar
        conversations={conversations}
        currentId={currentId}
        onSelect={selectConversation}
        onNew={newChat}
        onSignOut={onSignOut}
      />
      <div className="flex flex-col flex-1 min-w-0">
        <nav className="flex items-center gap-1 border-b border-border px-4 py-2">
          {(["chat", "finance", "connectors"] as const).map((v) => (
            <button
              key={v}
              type="button"
              onClick={() => setView(v)}
              className={[
                "rounded-md px-3 py-1.5 text-sm font-medium transition",
                view === v
                  ? "bg-accent-soft text-accent"
                  : "text-muted hover:bg-surface-muted hover:text-foreground",
              ].join(" ")}
            >
              {VIEW_LABELS[v]}
            </button>
          ))}
        </nav>
        {view === "chat" ? (
          <Chat
            messages={messages}
            loading={loading}
            error={error}
            onSend={send}
            digest={digest?.content ?? null}
            onGenerateDigest={generateDigest}
            digestBusy={digestBusy}
          />
        ) : view === "finance" ? (
          <Finance token={token} />
        ) : (
          <Connectors token={token} />
        )}
      </div>
    </main>
  );
}
