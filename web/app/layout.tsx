import type { Metadata } from "next";

import "./globals.css";

export const metadata: Metadata = {
  title: "CarDuka AI Agent",
  description: "Chat-first AI agent for Kenya's NCBA-backed car marketplace.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
