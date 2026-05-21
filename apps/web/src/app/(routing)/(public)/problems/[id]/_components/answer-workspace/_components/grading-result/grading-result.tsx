"use client";

// GradingResult: 採点結果の表示コンポーネント（R1-5）。
//   - useGetSubmission で 1.5s ポーリングして status を監視
//   - status 別に表示を分岐：
//       pending: スピナー + 「採点中...」
//       graded:  passed=true なら「正解」、それ以外は failureKind で分岐
//                  test_failed → 失敗テスト一覧
//                  timeout / oom / syntax / runtime → 種別メッセージ
//       failed:  「一時的なエラーです」+ 再試行ボタン (onRetry コールバック)
//
// 要件:
//   - docs/requirements/4-features/grading.md §採点結果表示
//   - docs/requirements/4-features/grading.md §受け入れ条件

import type { SubmissionTestResultItem } from "@/__generated__/api/types.gen";
import { Button } from "@/components/ui/button/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card/card";

import { useGetSubmission } from "../../../../_hooks/_fetch/use-get-submission/use-get-submission";

type GradingResultProps = {
  // submissionId: 採点対象。null の間はコンポーネント自体をマウントしない想定だが、
  //   万一渡された場合は useGetSubmission 側で enabled=false にして空表示する。
  submissionId: string;
  // onRetry: status='failed'（インフラ起因）時の再試行ボタン押下で呼ばれる。
  //   呼び出し側 (AnswerWorkspace) で submissionId をクリアし再 submit 可能にする。
  onRetry: () => void;
};

// FAILURE_KIND_LABELS: failureKind → 画面表示用日本語ラベル。
//   要件側「失敗系のユーザー観測」と一致させる：
//     test_failed: 「テスト不合格」
//     timeout:     「タイムアウト」（実行時間 5 秒超過）
//     oom:         「メモリ使用量超過」
//     syntax:      「構文エラー」
//     runtime:     「実行時エラー」
const FAILURE_KIND_LABELS: Record<string, string> = {
  test_failed: "テスト不合格",
  timeout: "タイムアウト",
  oom: "メモリ使用量超過",
  syntax: "構文エラー",
  runtime: "実行時エラー",
};

export const GradingResult = ({ submissionId, onRetry }: GradingResultProps) => {
  const { submission, error } = useGetSubmission(submissionId);

  // error: 404（他人の id / 不在）/ 401（セッション切れ）/ 500（一時障害）等。
  //   ApiErrorProvider のトーストでも通知されるが、本コンポーネント内にも
  //   メッセージを残してユーザーが状況を把握できるようにする。
  if (error !== null) {
    return (
      <ResultCard title="採点結果の取得に失敗しました" tone="destructive">
        <p className="text-sm text-muted-foreground">時間を置いて再度お試しください。</p>
      </ResultCard>
    );
  }

  // 初回取得待ちは pending と同じ「採点中」表示にする。
  //   ポーリング中の中間状態を空白で見せない（grading.md §採点結果表示
  //   「採点中はスピナーを表示」要件）。
  if (submission === undefined || submission.status === "pending") {
    return (
      <ResultCard title="採点中..." tone="muted">
        <div className="flex items-center gap-3">
          {/* スピナー: 標準的な Tailwind の animate-spin を使う */}
          <span
            aria-hidden="true"
            className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-muted-foreground border-t-transparent"
          />
          <p className="text-sm text-muted-foreground">
            サーバで実行・採点しています。少々お待ちください。
          </p>
        </div>
      </ResultCard>
    );
  }

  // failed: インフラ起因の確定失敗。再試行ボタンで AnswerWorkspace 側の
  //   submissionId クリア → 再 submit の流れに戻す。
  if (submission.status === "failed") {
    return (
      <ResultCard title="一時的なエラーが発生しました" tone="destructive">
        <p className="text-sm text-muted-foreground">
          採点処理に失敗しました。同じコードでもう一度お試しください。
        </p>
        <Button onClick={onRetry} className="mt-3" size="sm">
          再試行
        </Button>
      </ResultCard>
    );
  }

  // graded: 採点完了。passed=true なら「正解」、それ以外は failureKind で分岐。
  //   total / score / result を参照するため null チェックを挟む（ポーリング途中の
  //   中間状態で空 graded が返ることは Worker 契約上ないが、念のため）。
  if (submission.result === null || submission.result === undefined) {
    return (
      <ResultCard title="採点結果を取得できませんでした" tone="destructive">
        <p className="text-sm text-muted-foreground">時間を置いて再度お試しください。</p>
      </ResultCard>
    );
  }

  const { result } = submission;
  const score = submission.score ?? 0;
  const total = submission.totalCount ?? 0;

  // passed=true（全テスト通過）: 「正解」と通過数を強調表示。
  if (result.passed) {
    return (
      <ResultCard title="正解" tone="success">
        <div className="space-y-1 text-sm">
          <p>
            通過数:{" "}
            <span className="font-semibold">
              {score}/{total}
            </span>
          </p>
          <p className="text-muted-foreground">実行時間: {formatDurationMs(result.durationMs)}</p>
        </div>
      </ResultCard>
    );
  }

  // passed=false: failureKind で分岐。
  const kindLabel =
    result.failureKind != null ? (FAILURE_KIND_LABELS[result.failureKind] ?? "不合格") : "不合格";

  return (
    <ResultCard title={kindLabel} tone="destructive">
      <div className="space-y-2 text-sm">
        <p>
          通過数:{" "}
          <span className="font-semibold">
            {score}/{total}
          </span>
        </p>
        <p className="text-muted-foreground">実行時間: {formatDurationMs(result.durationMs)}</p>
        {/* 失敗テストの詳細は test_failed の時だけ価値がある。
            timeout / oom / syntax / runtime はそもそもテストが走らずまとめて
            「不合格」になるため、ここでは failed のテストケースのみ列挙する。 */}
        {result.failureKind === "test_failed" && <FailedCases items={result.testResults ?? []} />}
      </div>
    </ResultCard>
  );
};

// ResultCard: 4 種類のステータス表示で共通の枠を切り出した内部部品。
//   tone は枠線色のセマンティック分け（success / destructive / muted）。
type ResultCardProps = {
  title: string;
  tone: "success" | "destructive" | "muted";
  children: React.ReactNode;
};

const RESULT_CARD_TONE_BORDER: Record<ResultCardProps["tone"], string> = {
  // tone="success": 採点通過時の枠。Tailwind 既定の green-500 を使う
  //   (デザイントークンに正解専用色が無いため例外的に生カラー)。
  success: "border-green-500",
  destructive: "border-destructive",
  muted: "border-border",
};

const RESULT_CARD_TONE_TITLE: Record<ResultCardProps["tone"], string> = {
  success: "text-green-700",
  destructive: "text-destructive",
  muted: "",
};

const ResultCard = ({ title, tone, children }: ResultCardProps) => (
  <Card className={`border-2 ${RESULT_CARD_TONE_BORDER[tone]}`}>
    <CardHeader className="pb-3">
      <CardTitle className={`text-lg ${RESULT_CARD_TONE_TITLE[tone]}`}>{title}</CardTitle>
    </CardHeader>
    <CardContent>{children}</CardContent>
  </Card>
);

// FailedCases: 失敗したテストケースの一覧。
//   要件「失敗したテストケース名・期待値・実際の出力・差分を表示」に対応。
//   expected / actual は Worker 側で文字列に整形済 (string | null)。
const FailedCases = ({ items }: { items: SubmissionTestResultItem[] }) => {
  const failedOnly = items.filter((it) => !it.passed);
  if (failedOnly.length === 0) return null;
  return (
    <details className="mt-2 rounded-md border border-border p-3">
      <summary className="cursor-pointer text-sm font-medium">
        失敗したテストケース ({failedOnly.length})
      </summary>
      <ul className="mt-2 space-y-3">
        {failedOnly.map((it) => (
          // key: vitest の test 名 (it.name) は同 spec 内で一意。
          //   Worker 側 (submission_grade.go) も summary.Failures[].Name を
          //   そのまま渡すため、ここで index 等を足さなくても衝突しない。
          <li key={it.name} className="rounded-md bg-muted p-2 text-xs">
            <p className="font-semibold">{it.name}</p>
            {it.expected != null && (
              <p>
                <span className="text-muted-foreground">期待値: </span>
                <code className="break-all">{it.expected}</code>
              </p>
            )}
            {it.actual != null && (
              <p>
                <span className="text-muted-foreground">実際の出力: </span>
                <code className="break-all">{it.actual}</code>
              </p>
            )}
            {it.message != null && (
              <p className="mt-1 whitespace-pre-wrap text-muted-foreground">{it.message}</p>
            )}
          </li>
        ))}
      </ul>
    </details>
  );
};

// formatDurationMs: ミリ秒を「1234ms」「1.2s」の表示用に整形。
//   1000ms 未満は ms、超えたら s 表示で UI 上の読みやすさを優先。
const formatDurationMs = (ms: number): string => {
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
};
