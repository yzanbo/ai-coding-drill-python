// StatusBadge: ステータスを色付きバッジで表示する汎用部品。
//
//   tone は以下の 4 値：
//     - ok    : 成功（青、bg-primary/10）
//     - ng    : 失敗（赤、bg-destructive/10）
//     - warn  : 進行中・注意（橙、bg-amber-500/10）
//     - muted : 終了・無効（薄字、bg 無し）
//
//   従来 /me/generations は TONE_CLASS map、/me/history は inline 三項ネストで
//   同じ Tailwind 文字列をそれぞれ独立に書いていた。色設計を 1 箇所に集めて、
//   新画面で「採点中バッジ」「キャンセル済バッジ」等を出すときに迷わなくする。
//
//   ラベル文字列は親が持つ責務（ドメイン語彙：「成功」「採点中」「キャンセル済」
//   等）。本部品は tone と children だけ受け取り、見た目だけを規定する。

import { cn } from "@/lib/utils";

export type StatusTone = "ok" | "ng" | "warn" | "muted";

// TONE_CLASS: tone 値 → Tailwind クラス文字列。サイト全体でこのテーブルが SSoT。
//   ok/ng/warn は font-semibold で強調、muted は通常字（注意を引かない）。
const TONE_CLASS: Record<StatusTone, string> = {
  ok: "bg-primary/10 text-primary font-semibold",
  ng: "bg-destructive/10 text-destructive font-semibold",
  warn: "bg-amber-500/10 text-amber-600 font-semibold",
  muted: "text-muted-foreground",
};

// 全 tone 共通の枠線・余白・字サイズ。色 / 太字は tone 側に寄せる。
const BASE_CLASS = "rounded-md border border-border px-2 py-0.5 text-xs";

type StatusBadgeProps = {
  tone: StatusTone;
  children: React.ReactNode;
  className?: string;
};

export const StatusBadge = ({ tone, children, className }: StatusBadgeProps) => (
  <span className={cn(BASE_CLASS, TONE_CLASS[tone], className)}>{children}</span>
);
