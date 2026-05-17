import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";

import { SiteHeader } from "@/components/parts/site-header/site-header";
import { ApiErrorProvider } from "@/components/providers/api-error-provider/api-error-provider";
import { QueryClientProvider } from "@/components/providers/query-client-provider/query-client-provider";
import { Toaster } from "@/components/ui/sonner/sonner";

import "./globals.css";

// Geist / Geist_Mono: Next.js 同梱の Google Font ラッパ。CSS 変数に流して
//   globals.css の --font-sans / --font-mono から参照する。
const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "AI Coding Drill",
  description: "LLM が自動生成した TypeScript 問題をサンドボックスで採点する学習サイト。",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="ja" className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}>
      <body className="min-h-full flex flex-col">
        {/*
          Provider 階層:
            QueryClientProvider → ApiErrorProvider → アプリ本体
              ・QueryClientProvider が一番外（サーバ状態の入れ物）
              ・ApiErrorProvider は QueryClient に subscribe するので内側に置く
            Toaster は副作用無しの DOM 出力なので兄弟で問題ない。
        */}
        <QueryClientProvider>
          <ApiErrorProvider>
            <SiteHeader />
            {children}
          </ApiErrorProvider>
        </QueryClientProvider>
        <Toaster />
      </body>
    </html>
  );
}
