import type { Metadata } from "next";
import "./globals.css";
import "highlight.js/styles/github.css";
import { Toaster } from "@/components/ui/toaster";

export const metadata: Metadata = {
  title: "Replay Console",
  description: "Remote browser control console — live click / drag / typing replay + full agent chat",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="antialiased">
        {children}
        <Toaster />
      </body>
    </html>
  );
}
