import "./globals.css";
import type { ReactNode } from "react";

export const metadata = {
  title: "Brownfield Cartographer",
  description: "Semantic overview of legacy systems",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen overflow-x-hidden overflow-y-auto bg-zinc-950 text-zinc-100">
        {children}
      </body>
    </html>
  );
}
