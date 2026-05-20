"use client";

// GenerationStatusView: 生成ステータスをポーリングして UI を出し分ける本体。
//   - pending: 「生成中…」を表示し、引き続きポーリング
//   - completed: /problems/:problemId に自動遷移
//   - failed: 失敗メッセージ + 再試行ボタン（/problems/new に戻す）
//   要件: docs/requirements/4-features/problem-generation.md §生成ステータス画面
//
//   失敗種別（LLM スキーマ違反 / Sandbox 失敗 / Judge 不合格）はユーザーには区別せず
//   「生成に失敗しました」とだけ伝える（情報漏洩防止、要件 §画面）。

import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { Button } from "@/components/ui/button/button";

import { useGetProblemGenerationStatus } from "../../_hooks/_fetch/use-get-problem-generation-status/use-get-problem-generation-status";

type GenerationStatusViewProps = {
  requestId: string;
};

export const GenerationStatusView = ({ requestId }: GenerationStatusViewProps) => {
  const router = useRouter();
  const { status, isLoading, error } = useGetProblemGenerationStatus(requestId);

  // 完了したら問題詳細画面に自動遷移。
  //   useEffect で実行することで、レンダリング中の navigate を避ける（Next.js が警告を出すため）。
  //   replace を使うのは生成ステータス画面に戻れないようにするため（「戻る」で再ポーリングしても意味がない）。
  useEffect(() => {
    if (status?.status === "completed" && status.problemId) {
      router.replace(`/problems/${status.problemId}`);
    }
  }, [status, router]);

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
  if (error) {
    return (
      <div className="flex flex-col items-center gap-3 py-12 text-center">
        <p className="text-base font-semibold">生成状況を取得できませんでした</p>
        <p className="text-sm text-muted-foreground">時間を置いて再度お試しください。</p>
        <Button variant="outline" size="sm" onClick={() => router.refresh()}>
          再読み込み
        </Button>
      </div>
    );
  }

  if (status?.status === "failed") {
    return (
      <div className="flex flex-col items-center gap-3 py-12 text-center">
        <p className="text-base font-semibold">生成に失敗しました</p>
        <p className="text-sm text-muted-foreground">
          条件を変えるかしばらく時間を置いて、もう一度お試しください。
        </p>
        <Button onClick={() => router.replace("/problems/new")}>もう一度生成する</Button>
      </div>
    );
  }

  // completed の時点では useEffect でリダイレクトが走るのでチラ見え防止に空表示。
  if (status?.status === "completed") {
    return null;
  }

  // pending（ポーリング継続中）
  return (
    <div className="flex flex-col items-center gap-3 py-12 text-center">
      <p className="text-base font-semibold">生成中…</p>
      <p className="text-sm text-muted-foreground">
        AI
        が問題本文・テストケース・模範解答を生成しています。完了すると自動的に問題ページに移動します。
      </p>
    </div>
  );
};
