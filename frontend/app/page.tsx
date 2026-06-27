"use client";

import { TokenGate } from "@/app/TokenGate";
import { Workspace } from "@/app/Workspace";
import { useToken } from "@/app/useToken";

export default function Home() {
  const { token, ready, setToken, clearToken } = useToken();

  // Wait for the initial localStorage read so we don't flash the sign-in screen.
  if (!ready) {
    return <main className="min-h-dvh bg-background" />;
  }

  if (!token) {
    return <TokenGate onSubmit={setToken} />;
  }

  return <Workspace token={token} onSignOut={clearToken} />;
}
