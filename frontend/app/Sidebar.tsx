"use client";

import type { ConversationSummary } from "@/lib/api";

interface SidebarProps {
  /** Past conversations, newest first. */
  conversations: ConversationSummary[];
  /** The currently open conversation, or null for a fresh chat. */
  currentId: number | null;
  /** Open a past conversation. */
  onSelect: (id: number) => void;
  /** Start a new conversation. */
  onNew: () => void;
  /** Sign out (clear the token). */
  onSignOut: () => void;
}

/** Left rail: branding, "New chat", the conversation history list, and sign out. */
export function Sidebar({
  conversations,
  currentId,
  onSelect,
  onNew,
  onSignOut,
}: SidebarProps) {
  return (
    <aside className="flex h-dvh w-64 shrink-0 flex-col border-r border-border bg-surface-muted">
      <div className="flex items-baseline gap-2 px-4 py-4">
        <span className="font-serif text-xl tracking-tight text-foreground">
          Pragya
        </span>
        <span className="text-xs text-muted">personal assistant</span>
      </div>

      <div className="px-3">
        <button
          type="button"
          onClick={onNew}
          className="mb-2 flex w-full items-center gap-2 rounded-lg border border-border bg-surface px-3 py-2 text-sm font-medium text-foreground transition hover:border-accent"
        >
          <PlusIcon />
          New chat
        </button>
      </div>

      <nav className="pragya-scroll flex-1 overflow-y-auto px-2 py-1">
        {conversations.length === 0 ? (
          <p className="px-2 py-3 text-xs text-muted">No conversations yet.</p>
        ) : (
          <ul className="flex flex-col gap-0.5">
            {conversations.map((conversation) => (
              <li key={conversation.id}>
                <button
                  type="button"
                  onClick={() => onSelect(conversation.id)}
                  title={conversation.title}
                  className={[
                    "w-full truncate rounded-lg px-3 py-2 text-left text-sm transition",
                    conversation.id === currentId
                      ? "bg-surface text-foreground"
                      : "text-muted hover:bg-surface hover:text-foreground",
                  ].join(" ")}
                >
                  {conversation.title}
                </button>
              </li>
            ))}
          </ul>
        )}
      </nav>

      <div className="border-t border-border px-3 py-3">
        <button
          type="button"
          onClick={onSignOut}
          className="w-full rounded-md px-2.5 py-1.5 text-left text-xs font-medium text-muted transition hover:bg-surface hover:text-foreground"
        >
          Sign out
        </button>
      </div>
    </aside>
  );
}

function PlusIcon() {
  return (
    <svg
      width="15"
      height="15"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M12 5v14M5 12h14" />
    </svg>
  );
}
