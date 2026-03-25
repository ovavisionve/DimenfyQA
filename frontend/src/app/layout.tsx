import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "IG DM Engine",
  description: "Instagram DM automation platform",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="es" className="h-full antialiased">
      <body className="min-h-full font-sans">{children}</body>
    </html>
  );
}
