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

## Why（採用理由）

1. **バンドルサイズが Monaco 比で 10〜20 倍軽量（~200KB vs 2〜5MB）**
   - Lighthouse スコア・LCP・初回読み込み体験に直接効く
   - ポートフォリオで Web パフォーマンスを語る根拠になる
2. **Next.js App Router との統合摩擦が小さい**
   - Client Component に素直に乗り、SSR / Web Worker のハマりどころが Monaco より大幅に少ない
   - Monaco は Next.js 統合で `next-monaco-editor` 等のラッパーや WebWorker 配線が必要で、CSP・SSR と衝突しやすい
3. **モバイル・アクセシビリティが設計から考慮されている**
   - CodeMirror 6 は IME・タッチ・スクリーンリーダーをコア機能として再設計した世代で、Monaco の VS Code 由来設計より広い利用シーンに対応
4. **採点はサーバ側 Vitest で行うため、エディタの「IDE 完成度」は最重要ではない**
   - ブラウザ実行は不要で、必要なのは型診断・補完による即時フィードバックのみ
   - `@typescript/vfs` + `@valtown/codemirror-ts` で Monaco の 80% 程度の体験を遥かに軽量に実現でき、コスパが優れる
   - Sandpack / WebContainers のようなブラウザ内ランタイムはサーバ採点と二重実装になりセキュリティモデルとも不整合
5. **モジュラー設計で必要機能だけ取捨選択できる**
   - 拡張パッケージを選んで組み込むため、Monaco のように「全部入りで重い」を避けられる

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
