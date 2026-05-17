// cn: Tailwind のクラス文字列をまとめて 1 本にする道具。
//   - clsx: 条件分岐で「このクラスを足す / 足さない」を書きやすくする
//   - twMerge: 後ろに書いたクラスを優先して衝突を解消する（例: "p-2" + "p-4" → "p-4"）
//   shadcn/ui のコンポーネントが前提にしているヘルパなので、配置場所も同様に
//   lib 直下の単発ファイルに置く（frontend.md ディレクトリ構成節）。
import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
