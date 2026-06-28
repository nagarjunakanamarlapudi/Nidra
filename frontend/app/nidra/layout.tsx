import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Nidra | Mobile companion mock",
  description: "A mobile-first Nidra companion experience mock.",
};

export default function NidraLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return children;
}
