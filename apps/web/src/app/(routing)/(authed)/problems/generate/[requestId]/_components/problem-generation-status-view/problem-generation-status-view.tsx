"use client";

// ProblemGenerationStatusView: 生成ステータスをポーリングして UI を出し分ける本体。
//   - pending: 「生成中…」を表示し、引き続きポーリング
//   - completed: /problems/:problemId に自動遷移
//   - failed: 失敗メッセージ + 再試行ボタン（同じ条件で新規 generation_request を作り、
//     新しい /problems/generate/:newRequestId に置換遷移）
//   要件: docs/requirements/4-features/problem-generation.md §生成ステータス画面
//
//   失敗種別（LLM スキーマ違反 / Sandbox 失敗 / Judge 不合格）はユーザーには区別せず
//   「生成に失敗しました」とだけ伝える（情報漏洩防止、要件 §画面）。

import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { AttemptErrorList } from "@/components/parts/attempt-error-list/attempt-error-list";
import { GenerationProgress } from "@/components/parts/generation-progress/generation-progress";
import { LiveDuration } from "@/components/parts/live-duration/live-duration";
import { Button } from "@/components/ui/button/button";
import { useRetryMyGeneration } from "@/hooks/use-retry-my-generation/use-retry-my-generation";
import { formatDate } from "@/lib/utils/format-date";

import { useGetProblemGenerationStatus } from "../../_hooks/_fetch/use-get-problem-generation-status/use-get-problem-generation-status";

type ProblemGenerationStatusViewProps = {
  requestId: string;
};

export const ProblemGenerationStatusView = ({ requestId }: ProblemGenerationStatusViewProps) => {
  const router = useRouter();
  const { status, isLoading, isFetching, error, refetch } =
    useGetProblemGenerationStatus(requestId);
  // useRetryMyGeneration: 生成履歴ページと共有のフック。同じ条件で新規 generation_request
  //   を作り、成功後にその新しい requestId のステータス画面へ replace 遷移する。
  const retryMutation = useRetryMyGeneration();

  // onRetry: failed 状態のリクエストを再試行して、新しいリクエストの生成中画面に切り替える。
  //   replace を使う理由：戻るボタンで failed の旧画面に戻れないようにする
  //   （ポーリング済みの最終状態なので戻る価値が無い）。
  //   失敗時はトーストを ApiErrorProvider が出すので、ここでは握り潰す。
  const handleRetry = () => {
    retryMutation
      .retry(requestId)
      .then((res) => {
        router.replace(`/problems/generate/${res.id}`);
      })
      .catch(() => {
        // ApiErrorProvider 側でトースト出ているので無視。
      });
  };

  // 完了したら問題詳細画面に自動遷移。
  //   useEffect で実行することで、レンダリング中の navigate を避ける（Next.js が警告を出すため）。
  //   replace を使うのは生成ステータス画面に戻れないようにするため（「戻る」で再ポーリングしても意味がない）。
  //   依存は status?.status と status?.problemId に絞る：status オブジェクトは
  //   ポーリングのたびに新しい reference になるので、オブジェクト自体を deps に
  //   置くと完了後も replace が連発される。フィールド値だけ見れば値ベースで安定する。
  useEffect(() => {
    if (status?.status === "completed" && status.problemId) {
      router.replace(`/problems/${status.problemId}`);
    }
  }, [status?.status, status?.problemId, router]);

  if (isLoading) {
    return (
      <div className="flex flex-col items-center gap-3 py-12 text-center">
        <p className="text-base font-semibold">生成中…</p>
        <p className="text-sm text-muted-foreground">
          問題の準備をしています。少しお待ちください。
        </p>
      </div>
    );
  }

  // ステータス取得自体が失敗（404 / 通信断 等）。トーストは ApiErrorProvider が出すのでここではインライン補足のみ。
  //   isFetching=true は「再読み込み」ボタン押下後の refetch 中。
  //   ボタンを押した直後に押下感が消えると操作の手応えが分かりにくいので、文言を切り替えて押下中であることを示す。
  if (error) {
    return (
      <div className="flex flex-col items-center gap-3 py-12 text-center">
        <p className="text-base font-semibold">生成状況を取得できませんでした</p>
        <p className="text-sm text-muted-foreground">時間を置いて再度お試しください。</p>
        <Button variant="outline" size="sm" onClick={() => refetch()} disabled={isFetching}>
          {isFetching ? "再読み込み中…" : "再読み込み"}
        </Button>
      </div>
    );
  }

  if (status?.status === "failed") {
    return (
      <div className="mx-auto flex max-w-md flex-col gap-3 py-12">
        <p className="text-center text-base font-semibold">生成に失敗しました</p>
        <p className="text-center text-sm text-muted-foreground">
          条件を変えるかしばらく時間を置いて、もう一度お試しください。
        </p>
        {status.createdAt ? (
          <p className="text-center text-xs text-muted-foreground">
            開始: {formatDate(status.createdAt)} ／ 所要{" "}
            <LiveDuration createdAt={status.createdAt} completedAt={status.completedAt} />
          </p>
        ) : null}
        {/* 試行ごとのエラー履歴を折りたたみで提示。max_attempts_exceeded でも
            「3 回中、どの試行でどのカテゴリの error が起きたか」が分かる。 */}
        <AttemptErrorList attemptErrors={status.attemptErrors ?? []} />
        <div className="text-center">
          <Button onClick={handleRetry} disabled={retryMutation.isPending}>
            再試行
          </Button>
        </div>
      </div>
    );
  }

  // completed の時点では useEffect でリダイレクトが走るのでチラ見え防止に空表示。
  if (status?.status === "completed") {
    return null;
  }

  // pending（ポーリング継続中）：ステップインジケータ + 開始時刻 + 経過時間。
  //   経過時間は LiveDuration が setInterval で 1 秒ごとに自分だけ再描画する
  //   （ポーリング fetch 周期 1.5 秒に左右されない）。
  return (
    <div className="mx-auto flex max-w-md flex-col gap-6 py-12">
      <div className="text-center">
        <p className="text-base font-semibold">生成中…</p>
        <p className="mt-1 text-sm text-muted-foreground">
          完了すると自動的に問題ページに移動します。
        </p>
      </div>
      <GenerationProgress currentStep={status?.progressStep} variant="full" />
      {status?.createdAt ? (
        <p className="text-center text-xs text-muted-foreground">
          開始: {formatDate(status.createdAt)} ／ 経過{" "}
          <LiveDuration createdAt={status.createdAt} completedAt={status.completedAt} />
        </p>
      ) : null}
    </div>
  );
};
