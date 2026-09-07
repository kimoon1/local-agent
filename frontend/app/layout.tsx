import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = { title: "Local Web Agent", description: "LM Studio 기반 웹 검색 에이전트" };

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="ko"><body>{children}</body></html>;
}
