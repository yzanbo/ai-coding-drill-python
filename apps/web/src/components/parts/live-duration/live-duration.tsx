"use client";

// LiveDuration: 生成リクエストの所要時間を表示する小さな部品。
//   completedAt が無い（進行中）行は内部タイマで 1 秒ごとに再レンダリングし、
//   秒数がリアルタイムに進んで見える。completedAt が確定済みなら静的表示で
//   タイマは起動しない（無駄な再レンダリングと電池消費を避ける）。
//
//   ページ全体の再レンダリングを避けるために独立コンポーネントに切り出し、
//   useState による tick はこのコンポーネント内に閉じ込める（親の
//   GenerationRow / リスト全体は再描画されない）。

import { useEffect, useState } from "react";

// formatDuration: 経過時間（ms）を「12 秒」「3 分 5 秒」表記に丸める。
//   end が無い時は now を使う側で渡す（本関数は純粋計算に保つ）。
const formatDuration = (start: number, end: number): string => {
  if (!Number.isFinite(start) || !Number.isFinite(end)) return "—";
  const sec = Math.max(0, Math.floor((end - start) / 1000));
  if (sec < 60) return `${sec} 秒`;
  return `${Math.floor(sec / 60)} 分 ${sec % 60} 秒`;
};

// TICK_INTERVAL_MS: 進行中行の表示更新間隔。
//   秒単位の表示なので 1 秒間隔で十分。タブ非アクティブ中も setInterval は
//   一時停止する（ブラウザの throttling）ため、追加のガードは不要。
const TICK_INTERVAL_MS = 1000;

type LiveDurationProps = {
  createdAt: string;
  completedAt: string | null | undefined;
};

export const LiveDuration = ({ createdAt, completedAt }: LiveDurationProps) => {
  const start = new Date(createdAt).getTime();
  // completedAt があれば固定値、無ければ now を毎秒更新する。
  const isInFlight = !completedAt;
  const [now, setNow] = useState<number>(() => Date.now());

  useEffect(() => {
    // 完了済の行ではタイマを起動しない（再レンダリング不要）。
    if (!isInFlight) return;
    const id = setInterval(() => setNow(Date.now()), TICK_INTERVAL_MS);
    return () => clearInterval(id);
  }, [isInFlight]);

  const end = completedAt ? new Date(completedAt).getTime() : now;
  return <>{formatDuration(start, end)}</>;
};
