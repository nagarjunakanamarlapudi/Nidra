"use client";

import {
  useEffect,
  useRef,
  useState,
  type FormEvent,
  type KeyboardEvent,
} from "react";
import type { Effort } from "@/lib/api";

export type Role = "user" | "assistant";

export interface DisplayMessage {
  id: string;
  role: Role;
  text: string;
}

interface ChatProps {
  /** Messages of the current conversation. */
  messages: DisplayMessage[];
  /** Whether a reply is in flight. */
  loading: boolean;
  /** Error to surface above the composer, if any. */
  error: string | null;
  /** Send the composed message at the chosen reasoning effort. */
  onSend: (text: string, effort: Effort | undefined) => void;
  /** Latest digest text, shown on the empty state (null = none yet). */
  digest: string | null;
  /** Generate a digest now. */
  onGenerateDigest: () => void;
  /** Whether a digest is being generated. */
  digestBusy: boolean;
}

/** The chat surface: message list, loading/error states, and the composer. */
export function Chat({
  messages,
  loading,
  error,
  onSend,
  digest,
  onGenerateDigest,
  digestBusy,
}: ChatProps) {
  const [draft, setDraft] = useState("");
  const [effort, setEffort] = useState<Effort | "auto">("auto");
  const scrollRef = useRef<HTMLDivElement>(null);

  // Keep the latest message in view as the conversation grows.
  useEffect(() => {
    scrollRef.current?.scrollTo({
      top: scrollRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [messages, loading]);

  function submit() {
    const text = draft.trim();
    if (!text || loading) {
      return;
    }
    setDraft("");
    onSend(text, effort === "auto" ? undefined : effort);
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    submit();
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    // Enter sends; Shift+Enter inserts a newline.
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      submit();
    }
  }

  const isEmpty = messages.length === 0;

  return (
    <div className="flex h-dvh flex-1 flex-col">
      <div
        ref={scrollRef}
        className="pragya-scroll flex-1 overflow-y-auto px-5 py-6"
      >
        {isEmpty && !loading ? (
          <div className="mx-auto flex h-full max-w-2xl flex-col items-center justify-center gap-6 text-center">
            <div>
              <p className="font-serif text-2xl text-foreground">Good to see you.</p>
              <p className="mt-2 max-w-xs text-sm text-muted">
                Ask a question, jot something to remember, or just say hello.
              </p>
            </div>
            <TodayDigest digest={digest} onGenerate={onGenerateDigest} busy={digestBusy} />
          </div>
        ) : (
          <ul className="mx-auto flex max-w-2xl flex-col gap-4">
            {messages.map((message) => (
              <li key={message.id}>
                <MessageBubble role={message.role} text={message.text} />
              </li>
            ))}
            {loading ? (
              <li>
                <ThinkingBubble />
              </li>
            ) : null}
          </ul>
        )}
      </div>

      <div className="mx-auto w-full max-w-2xl px-5 pb-5">
        {error ? (
          <div
            role="alert"
            className="mb-3 rounded-lg border border-danger/30 bg-danger/10 px-3.5 py-2.5 text-sm text-danger"
          >
            {error}
          </div>
        ) : null}

        <form
          onSubmit={handleSubmit}
          className="rounded-2xl border border-border bg-surface p-2 shadow-sm focus-within:border-accent focus-within:ring-2 focus-within:ring-accent/15"
        >
          <textarea
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={handleKeyDown}
            rows={1}
            placeholder="Message Pragya…"
            className="pragya-scroll max-h-40 min-h-[2.5rem] w-full resize-none bg-transparent px-2.5 py-2 text-sm text-foreground outline-none placeholder:text-muted/70"
          />
          <div className="flex items-center justify-between gap-2 pl-1 pt-1">
            <label className="flex items-center gap-1.5 text-xs text-muted">
              <span>Reasoning</span>
              <select
                value={effort}
                onChange={(event) => setEffort(event.target.value as Effort | "auto")}
                aria-label="Reasoning effort"
                className="rounded-md border border-border bg-surface px-1.5 py-1 text-xs text-foreground outline-none transition focus:border-accent"
              >
                <option value="auto">Auto</option>
                <option value="low">Low</option>
                <option value="medium">Medium</option>
                <option value="high">High</option>
              </select>
            </label>
            <button
              type="submit"
              disabled={!draft.trim() || loading}
              aria-label="Send message"
              className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-accent text-white transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40"
            >
              <SendIcon />
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

function TodayDigest({
  digest,
  onGenerate,
  busy,
}: {
  digest: string | null;
  onGenerate: () => void;
  busy: boolean;
}) {
  return (
    <div className="w-full max-w-md rounded-2xl border border-border bg-surface p-4 text-left shadow-sm">
      <div className="mb-2 flex items-center justify-between">
        <span className="text-xs font-medium uppercase tracking-wider text-muted">
          Today&apos;s digest
        </span>
        <button
          type="button"
          onClick={onGenerate}
          disabled={busy}
          className="rounded-md px-2 py-1 text-xs font-medium text-accent transition hover:bg-surface-muted disabled:cursor-not-allowed disabled:opacity-40"
        >
          {busy ? "Generating…" : digest ? "Refresh" : "Generate"}
        </button>
      </div>
      {digest ? (
        <p className="whitespace-pre-wrap text-sm leading-relaxed text-foreground">{digest}</p>
      ) : (
        <p className="text-sm text-muted">
          No digest yet — generate one now, or it&apos;ll arrive on schedule.
        </p>
      )}
    </div>
  );
}

function MessageBubble({ role, text }: { role: Role; text: string }) {
  const isUser = role === "user";
  return (
    <div className={isUser ? "flex justify-end" : "flex justify-start"}>
      <div
        className={[
          "max-w-[85%] whitespace-pre-wrap break-words rounded-2xl px-4 py-2.5 text-sm leading-relaxed",
          isUser
            ? "rounded-br-sm bg-[var(--bubble-user)] text-[var(--bubble-user-text)]"
            : "rounded-bl-sm border border-border bg-[var(--bubble-assistant)] text-foreground",
        ].join(" ")}
      >
        {text}
      </div>
    </div>
  );
}

function ThinkingBubble() {
  return (
    <div className="flex justify-start">
      <div className="flex items-center gap-1.5 rounded-2xl rounded-bl-sm border border-border bg-[var(--bubble-assistant)] px-4 py-3.5">
        <span className="pragya-dot h-1.5 w-1.5 rounded-full bg-muted" />
        <span className="pragya-dot h-1.5 w-1.5 rounded-full bg-muted" />
        <span className="pragya-dot h-1.5 w-1.5 rounded-full bg-muted" />
      </div>
    </div>
  );
}

function SendIcon() {
  return (
    <svg
      width="18"
      height="18"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M22 2 11 13" />
      <path d="m22 2-7 20-4-9-9-4 20-7z" />
    </svg>
  );
}
