import type { Metadata } from "next";

import "./globals.css";

export const metadata: Metadata = {
  title: "Arcis",
  description: "Know where your money goes. Understand what to do next.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
