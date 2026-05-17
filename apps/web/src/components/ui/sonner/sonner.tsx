"use client";

// shadcn/ui の Sonner ラッパ。
//   トースト表示用。`<Toaster />` を root layout に 1 個置くと、どこからでも
//   `toast.success("...")` / `toast.error("...")` が呼べる。
//   公式: https://ui.shadcn.com/docs/components/sonner
import { Toaster as SonnerToaster, type ToasterProps } from "sonner";

export const Toaster = (props: ToasterProps) => {
  return (
    <SonnerToaster
      // position: 視線が落ちにくい右下に固定。
      position="bottom-right"
      // richColors: 成功 / エラーで色付きの分かりやすい配色にする。
      richColors
      // closeButton: トーストに × ボタンを表示する。
      closeButton
      {...props}
    />
  );
};
