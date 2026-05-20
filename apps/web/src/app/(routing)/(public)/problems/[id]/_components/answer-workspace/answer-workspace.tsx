"use client";

// AnswerWorkspace: コード入力 + 「実行」ボタンをまとめた解答エリア（R1-4）。
//   - 子の CodeEditor（CodeMirror 6）でユーザーが TS コードを書く
//   - 入力内容は localStorage に保存して、誤遷移時に復元する
//     （要件 problem-display-and-answer.md §ビジネスルール 任意機能）
//   - 「実行」ボタン挙動：
//     - ゲスト：/login?next=/problems/:id にリダイレクト
//     - 認証ユーザー：POST /api/submissions、202 + submissionId を取得
//   - 採点結果のポーリング表示は R1-5 のスコープ。R1-4 では「送信を受け付けました」
//     のフィードバックまでに留める。

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button/button";
import { useGetAuthMe } from "@/hooks/use-get-auth-me/use-get-auth-me";

import { usePostSubmission } from "../../_hooks/_fetch/use-post-submission/use-post-submission";
import { CodeEditor } from "./_components/code-editor/code-editor";

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

  const submission = usePostSubmission();

  const handleRun = () => {
    // 認証判定中は何もしない（ボタン disabled 側で抑制しているが二重防御）。
    if (isAuthLoading) return;
    if (isUnauthenticated || !isAuthenticated) {
      // /login?next=/problems/:id にリダイレクト（要件 §「実行」ボタン）。
      const next = `/problems/${problemId}`;
      router.push(`/login?next=${encodeURIComponent(next)}`);
      return;
    }
    submission.submitAnswer({ problemId, code });
  };

  return (
    <section aria-label="解答エリア" className="flex flex-col gap-4">
      <h2 className="text-sm font-semibold">解答</h2>

      <CodeEditor value={code} onChange={setCode} />

      <div className="flex items-center gap-3">
        <Button type="button" onClick={handleRun} disabled={submission.isPending || isAuthLoading}>
          {submission.isPending ? "送信中..." : "実行"}
        </Button>

        {submission.data ? (
          <p className="text-xs text-muted-foreground" role="status">
            解答を受け付けました（submissionId: {submission.data.submissionId}）。採点結果の表示は
            R1-5 で実装予定です。
          </p>
        ) : null}

        {submission.error ? (
          <p className="text-xs text-destructive" role="alert">
            送信に失敗しました（status: {submission.error.status}
            ）。時間を置いて再試行してください。
          </p>
        ) : null}
      </div>
    </section>
  );
};
