"use client";

// AttemptErrorList: failed 行の試行ごとエラー履歴を折りたたみ <details> で見せる。
//
//   API は最大 MaxAttempts (=3) 回ぶんの AttemptError を attemptErrors として返す
//   （Worker が jobs.MarkFailed / MarkDead のたびに append した jobs.attempt_errors
//    JSONB array、本人のリクエストのみ取得可能）。
//
//   表示要素：試行番号 / 失敗理由タグの日本語ラベル / 生エラー文字列 / 失敗時刻。
//   生エラー文字列は Worker 側で 1000 文字に truncate 済。本人のジョブの本人への
//   表示なので情報漏洩懸念は無い（user_id 一致 WHERE で他人の行は取得経路ゼロ）。
//
//   要素 0 件なら何も描画しない（呼び出し側で if (attemptErrors.length > 0) ガード不要）。

import type { AttemptError, FailureReasonTag } from "./types";

// FAILURE_REASON_SHORT_LABELS: 試行ごと表示用の短ラベル（バッジ風）。
//   page.tsx の FAILURE_MESSAGES（フル文言）とは別建て：1 試行 1 行で並べるため
//   短く揃える。両方の文言が DRY でないように見えるが、用途が違う（行内バッジ vs
//   メイン表示文言）ので分けて持つ方が改修しやすい。
const FAILURE_REASON_SHORT_LABELS: Record<FailureReasonTag, string> = {
  llm_unauthorized: "AI 認証失敗",
  llm_cost_exceeded: "コスト上限超過",
  judge_below_threshold: "品質スコア不足",
  sandbox_failed: "テスト不合格",
  sandbox_infrastructure: "実行環境エラー",
  llm_invalid_output: "AI 応答形式不正",
  llm_rate_limit: "AI レート制限",
  llm_timeout: "AI タイムアウト",
  llm_schema_invalid: "AI 出力 schema 違反",
  max_attempts_exceeded: "原因不明",
};

// formatFailedAt: ISO → "HH:mm:ss"。試行間の時間差感覚を秒精度で見せる。
//   日付は親の formatDate と被るので時刻だけ。
const formatFailedAt = (iso: string): string => {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  const hh = String(d.getHours()).padStart(2, "0");
  const mi = String(d.getMinutes()).padStart(2, "0");
  const ss = String(d.getSeconds()).padStart(2, "0");
  return `${hh}:${mi}:${ss}`;
};

type AttemptErrorListProps = {
  attemptErrors: AttemptError[];
  className?: string;
};

export const AttemptErrorList = ({ attemptErrors, className }: AttemptErrorListProps) => {
  if (attemptErrors.length === 0) return null;

  return (
    <details className={className}>
      <summary className="cursor-pointer text-xs text-muted-foreground hover:text-foreground">
        詳細（{attemptErrors.length} 回分の試行エラー）
      </summary>
      <ol className="mt-2 flex flex-col gap-2 text-xs">
        {attemptErrors.map((err) => (
          <li
            // attempt 番号は MarkDead 経路で 0 が入り得るが、failedAt は
            // server-side で NOW().UTC() なのでナノ秒精度で一意。array の順序も
            // 取得時点で固定（再フェッチで並べ替わらない）ため key として安定。
            key={err.failedAt}
            className="rounded-md border border-border bg-muted/40 p-2"
          >
            <div className="flex items-center gap-2 font-semibold">
              <span className="rounded-md border border-border bg-background px-2 py-0.5 text-xs">
                試行 {err.attempt > 0 ? err.attempt : "—"}
              </span>
              <span className="rounded-md border border-border bg-destructive/10 px-2 py-0.5 text-xs text-destructive">
                {FAILURE_REASON_SHORT_LABELS[err.failureReason] ?? err.failureReason}
              </span>
              <span className="text-muted-foreground">{formatFailedAt(err.failedAt)}</span>
            </div>
            <pre className="mt-1 whitespace-pre-wrap break-all text-[11px] text-muted-foreground">
              {err.message}
            </pre>
          </li>
        ))}
      </ol>
    </details>
  );
};
