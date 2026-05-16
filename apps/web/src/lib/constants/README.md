# lib/constants/

## lib/constants/ とは何か

**サイト全体で使う定数**（ルートパス・列挙値の表示ラベル・ページサイズ既定値・タイムアウト値等）
の置き場。コード中に裸の文字列・数値（マジック文字列・マジックナンバー）を散らさないため、
変更点を 1 か所に集めます。

代表例（このプロジェクトで想定）：

- `routes.ts`（`/login`、`/problems`、`/problems/[id]` 等のパス）
- `pagination.ts`（既定の `page-size`、`max-page-size` の上限）
- `difficulty-labels.ts`（`easy` / `medium` / `hard` の日本語表示ラベル対応表）
- `polling.ts`（採点ジョブのポーリング間隔とタイムアウト）

## 役目

- 値を 1 か所に集める。変更時に grep ではなく `import` から辿れる状態を保つ
- 列挙値（API の `string` リテラルユニオン）と **表示ラベルの対応表**を持つ
- 型は `as const` か `Readonly<...>` で書き換え不可にする

## 配置と命名

- 1 トピック 1 ファイル：`routes.ts` / `pagination.ts` 等
- 列挙ラベルは `Record<EnumType, string>` 型で書く：
  ```ts
  // difficulty-labels.ts
  import type { Difficulty } from "@/__generated__/api/types";

  export const DIFFICULTY_LABELS: Readonly<Record<Difficulty, string>> = {
    easy: "やさしい",
    medium: "ふつう",
    hard: "むずかしい",
  };
  ```
- 定数識別子は `SCREAMING_SNAKE_CASE`

## やってはいけないこと

- ❌ React の値（`useState` 結果等）をここに置く（定数ではない）
- ❌ 列挙値の型を **手書きする**（API レスポンスと同期しなくなる、`__generated__/api/types` を使う）
- ❌ 1 機能でしか使わない値をここに置く（ローカルに留める、コロケーション）
