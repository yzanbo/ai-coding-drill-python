"use client";

// AnswerWorkspace: コード入力 + 「実行」ボタンをまとめた解答エリア。
//   - 子の CodeEditor（CodeMirror 6）でユーザーが TS コードを書く
//   - 入力内容は localStorage に保存して、誤遷移時に復元する
//     （要件 problem-display-and-answer.md §ビジネスルール 任意機能）
//   - 「実行」ボタン挙動：
//     - ゲスト：/login?next=/problems/:id にリダイレクト
//     - 認証ユーザー：POST /api/submissions、202 + submissionId を取得
//   - submit 成功後は GradingResult を mount してポーリング表示（R1-5）。
//     インフラ起因失敗時は再試行ボタンで submissionId をクリアして再 submit 可能に。

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button/button";
import { useGetAuthMe } from "@/hooks/use-get-auth-me/use-get-auth-me";

import { usePostSubmission } from "../../_hooks/_fetch/use-post-submission/use-post-submission";
import { CodeEditor } from "./_components/code-editor/code-editor";
import { GradingResult } from "./_components/grading-result/grading-result";

type AnswerWorkspaceProps = {
  problemId: string;
};

// DEFAULT_CODE: 編集前の初期テンプレ。
//   ユーザーが空状態で「実行」を押すのを減らすため、関数シグネチャだけ用意する。
//   問題ごとの仕様（引数の型・名前）は LLM 生成側で揃わないので、最低限の足場のみ。
const DEFAULT_CODE = `// ここに解答を書いてください
export const solve = (input: unknown) => {
  return null;
};
`;

// localStorageKey: 問題ごとに別キーで保存する（誤遷移時に各問題のドラフトを復元）。
const localStorageKey = (problemId: string) => `ai-coding-drill:answer:${problemId}`;

export const AnswerWorkspace = ({ problemId }: AnswerWorkspaceProps) => {
  const router = useRouter();
  const { isAuthenticated, isUnauthenticated, isLoading: isAuthLoading } = useGetAuthMe();

  // code: エディタの現在値。SSR でも一意なため初期値は固定文字列。
  //   初回 mount 時に localStorage から復元する。
  const [code, setCode] = useState<string>(DEFAULT_CODE);
  const [restored, setRestored] = useState(false);

  // localStorage 復元（client only）。
  //   localStorage は SSR では参照できないので useEffect に閉じる。
  useEffect(() => {
    const saved = window.localStorage.getItem(localStorageKey(problemId));
    if (saved != null) setCode(saved);
    setRestored(true);
  }, [problemId]);

  // 入力ごとに localStorage に保存。
  //   useEffect の deps に code を入れているので毎キーストロークで書く形になる。
  //   localStorage は同期 API で実用上問題なし（数 ms）。デバウンス導入は
  //   ボトルネックが見えた時に検討する（YAGNI）。
  useEffect(() => {
    if (!restored) return; // 初回復元前の DEFAULT_CODE で上書きしない
    window.localStorage.setItem(localStorageKey(problemId), code);
  }, [code, problemId, restored]);

  // submissionId: 採点ジョブのキー。submit 成功 → ポーリング → 結果取得 → クリア
  //   というライフサイクルで持つ。null の間は GradingResult をマウントしない。
  const [submissionId, setSubmissionId] = useState<string | null>(null);

  const submission = usePostSubmission({
    onSuccess: (data) => {
      // submit 成功時に submissionId を確定 → GradingResult のマウントで
      // ポーリング開始（useGetSubmission の enabled が true に切り替わる）。
      setSubmissionId(data.submissionId);
    },
  });

  // submissionErrorMessage: status から日本語メッセージに変換。
  //   生の status コードは UI に出さず、ユーザーが取れる次の行動を文章にする。
  //   - 401: セッション切れ。再ログイン誘導。
  //   - 404: 問題が消えた / soft delete された。一覧に戻す案内。
  //   - 422: バリデーション失敗（コード長 / UUID 形式）。書き直し案内。
  //   - 429: レート制限。少し待つ案内。
  //   - その他 (5xx 等): 一時的な障害として再試行案内。
  const submissionErrorMessage = ((): string | null => {
    if (!submission.error) return null;
    switch (submission.error.status) {
      case 401:
        return "ログインの有効期限が切れました。再度ログインしてください。";
      case 404:
        return "この問題は見つかりませんでした。一覧から再度選び直してください。";
      case 422:
        return "解答コードの形式に問題があります。内容を見直して再送信してください。";
      case 429:
        return "送信回数が多すぎます。少し時間を置いてから再試行してください。";
      default:
        return "送信に失敗しました。時間を置いて再試行してください。";
    }
  })();

  const handleRun = () => {
    // 認証判定中は何もしない（ボタン disabled 側で抑制しているが二重防御）。
    if (isAuthLoading) return;
    if (isUnauthenticated || !isAuthenticated) {
      // /login?next=/problems/:id にリダイレクト（要件 §「実行」ボタン）。
      const next = `/problems/${problemId}`;
      router.push(`/login?next=${encodeURIComponent(next)}`);
      return;
    }
    // 連打防止のため進行中の submissionId は事前にクリア（再 submit 時の旧結果表示を防ぐ）。
    setSubmissionId(null);
    submission.submitAnswer({ problemId, code });
  };

  // handleRetry: GradingResult が status='failed'（インフラ起因）時に呼ぶ。
  //   submissionId をクリアして GradingResult をアンマウント → ユーザーは
  //   通常の「実行」ボタンで同じコードを再送信できる。
  const handleRetry = () => {
    setSubmissionId(null);
  };

  return (
    <section aria-label="解答エリア" className="flex flex-col gap-4">
      <h2 className="text-sm font-semibold">解答</h2>

      <CodeEditor value={code} onChange={setCode} />

      <div className="flex items-center gap-3">
        <Button type="button" onClick={handleRun} disabled={submission.isPending || isAuthLoading}>
          {submission.isPending ? "送信中..." : "実行"}
        </Button>

        {submissionErrorMessage ? (
          <p className="text-xs text-destructive" role="alert">
            {submissionErrorMessage}
          </p>
        ) : null}
      </div>

      {/* GradingResult: submit 成功後にだけマウント。pending 中は内部でスピナー、
          graded / failed で結果表示。failed 時は onRetry で submissionId クリア。 */}
      {submissionId !== null ? (
        <GradingResult submissionId={submissionId} onRetry={handleRetry} />
      ) : null}
    </section>
  );
};
