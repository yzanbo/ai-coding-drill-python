"use client";

// ProblemGenerationStatusView: 生成ステータスをポーリングして UI を出し分ける本体。
//   - pending: 「生成中…」を表示し、引き続きポーリング
//   - completed: /problems/:problemId に自動遷移
//   - failed: 失敗メッセージ + 再試行ボタン（/problems/new に戻す）
//   要件: docs/requirements/4-features/problem-generation.md §生成ステータス画面
//
//   失敗種別（LLM スキーマ違反 / Sandbox 失敗 / Judge 不合格）はユーザーには区別せず
//   「生成に失敗しました」とだけ伝える（情報漏洩防止、要件 §画面）。

import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { GenerationProgress } from "@/components/parts/generation-progress/generation-progress";
import { LiveDuration } from "@/components/parts/live-duration/live-duration";
import { Button } from "@/components/ui/button/button";
import { formatDate } from "@/lib/utils/format-date";

import { useGetProblemGenerationStatus } from "../../_hooks/_fetch/use-get-problem-generation-status/use-get-problem-generation-status";

type ProblemGenerationStatusViewProps = {
  requestId: string;
};

export const ProblemGenerationStatusView = ({ requestId }: ProblemGenerationStatusViewProps) => {
  const router = useRouter();
  const { status, isLoading, isFetching, error, refetch } =
    useGetProblemGenerationStatus(requestId);

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
      <div className="mx-auto flex max-w-md flex-col items-center gap-3 py-12 text-center">
        <p className="text-base font-semibold">生成に失敗しました</p>
        <p className="text-sm text-muted-foreground">
          条件を変えるかしばらく時間を置いて、もう一度お試しください。
        </p>
        {status.createdAt ? (
          <p className="text-xs text-muted-foreground">
            開始: {formatDate(status.createdAt)} ／ 所要{" "}
            <LiveDuration createdAt={status.createdAt} completedAt={status.completedAt} />
          </p>
        ) : null}
        <Button onClick={() => router.replace("/problems/new")}>もう一度生成する</Button>
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
