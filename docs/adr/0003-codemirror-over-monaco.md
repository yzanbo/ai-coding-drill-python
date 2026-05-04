# 0003. コードエディタに CodeMirror 6 を採用（Monaco Editor 不採用）

- **Status**: Accepted
- **Date**: 2026-04-25
- **Decision-makers**: 神保 陽平

## Context（背景・課題）

ブラウザ上で TypeScript コードを書かせるエディタコンポーネントが必要。

- スタック：Next.js（App Router）
- 採点はサーバ側（Vitest）で行う = ブラウザ実行は不要
- バンドルサイズ・LCP・Lighthouse スコアを意識したい
- インライン型診断（即時フィードバック）があると UX が向上
- モバイル・アクセシビリティも考慮したい

## Decision（決定内容）

**CodeMirror 6** を採用。`@typescript/vfs` + `@valtown/codemirror-ts` でブラウザ内型診断・補完を実現する。

## Alternatives Considered（検討した代替案）

| 候補 | 概要 | 採用しなかった理由 |
|---|---|---|
| Monaco Editor | VS Code の編集器、TypeScript IntelliSense 完備 | バンドル 2〜5MB、Next.js SSR/Worker のハマりどころ多数、モバイル・a11y が弱い |
| CodeMirror 6 | モジュラー、軽量（~200KB） | （採用） |
| Ace Editor | 老舗 | TS 対応が弱く、メンテも停滞気味 |
| Shiki + textarea | ハイライトのみ | 型診断が無く学習 UX で劣る |
| Sandpack（CodeSandbox） | ブラウザ内ランタイム | サーバ採点と二重実装になり、セキュリティモデルとも不整合 |
| StackBlitz WebContainers | Node.js を Browser で動かす | COOP/COEP ヘッダ要件が厳しく、Next.js との統合が複雑 |

## Consequences（結果・トレードオフ）

### 得られるもの
- バンドルサイズが Monaco 比で 10〜20 倍軽量、Lighthouse スコア・LCP に好影響
- Next.js Client Component に素直に乗る（SSR / Worker のハマりなし）
- モバイル・アクセシビリティが設計から考慮されている
- `@typescript/vfs` でサーバ採点前のローカル型フィードバック（200〜500ms）を実現

### 失うもの・受容するリスク
- Monaco の「VS Code そっくり」の完成度は得られない
- IntelliSense は Monaco に比べると 80% 程度の体験
- ブラウザ内型診断は自前で配線が必要（Monaco の標準 tsserver は使えない）

### 将来の見直しトリガー
- ユーザー要望で「VS Code そっくりの体験」が必須になった場合
- ブラウザ内 Vitest 実行などの大規模機能を入れる場合（その時は WebContainers も再検討）

## References

- [02-architecture.md: Frontend](../requirements/2-foundation/02-architecture.md#frontend)
- [05-runtime-stack.md: フロントエンド](../requirements/2-foundation/05-runtime-stack.md#フロントエンド)
