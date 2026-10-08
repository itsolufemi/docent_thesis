import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Smart Turn Human Recording Lab",
  description:
    "A local guided recorder for the Docent Smart Turn evaluation suite.",
  icons: {
    icon: "/favicon.svg",
    shortcut: "/favicon.svg",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
