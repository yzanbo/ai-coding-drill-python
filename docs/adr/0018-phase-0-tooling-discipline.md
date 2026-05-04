# 0018. 補完ツール（Knip / lefthook / commitlint / syncpack）を Phase 0 から導入

- **Status**: Accepted
- **Date**: 2026-05-03
- **Decision-makers**: 神保 陽平

## Context（背景・課題）

リポジトリの初期セットアップ時点で、以下の補完ツールを **Phase 0 で導入するか / 必要になるまで遅延するか** を決める必要がある：

- **Knip**：未使用の export / 依存 / ファイルの検出
- **lefthook**：Git フック管理（pre-commit / commit-msg）
- **commitlint**：Conventional Commits 規約に基づくコミットメッセージ検証
- **syncpack**：モノレポ内の `package.json` バージョン整合性強制

このプロジェクトの設計原則 ([CLAUDE.md](../../.claude/CLAUDE.md)) は「YAGNI：使うか分からない抽象化を先取りで作らない」を掲げている。これに従えば「必要になってから導入」が自然な選択肢に見える。

しかし上記ツールには、**他の YAGNI 対象（例：抽象化レイヤ・将来の機能要件）と異なる性質**がある：**途中導入時の修正コストが、放置期間に対して線形〜超線形に膨張する**。具体的には：

- **commitlint**：過去のコミット履歴は遡及修正不可。Phase 4 で導入しても、Phase 0〜3 のコミット履歴は規約外のまま残る
- **Knip**：Phase 4 で導入すると、蓄積した未使用コード・依存を一斉検出することになり、削除可否を個別判断する作業に大きな時間がかかる
- **syncpack**：バージョンずれが積もると、一括修正に動作リスクが伴う（依存関係の互換性を都度検証する必要）
- **lefthook**：自体の途中導入コストは低いが、上記ツールを動かすフックを後から差し込むだけのフレームワークなので、上記と同じく「動かす対象」が積もる前に入れる方が安い

つまり「YAGNI で導入を遅延する」と「将来の修正コストに変換するだけ」になる、という非対称性がある。

なお Biome は [ADR 0013](./0013-biome-for-tooling.md) で Phase 0 採用が確定済みだが、本 ADR では Biome 以外の補完ツール群について **Phase 0 導入の方針自体** を決定対象とする。

## Decision（決定内容）

**補完ツール（Knip / lefthook / commitlint / syncpack）を Phase 0（リポジトリ初期セットアップ時）から導入する。**

- 設定は `packages/config/` 配下に集約し、各アプリ・パッケージから参照
- lefthook の pre-commit フックで Biome / 型チェックを起動
- lefthook の commit-msg フックで commitlint を起動
- Knip / syncpack は CI（GitHub Actions）でも実行し、PR レベルで違反を弾く
- 導入が遅れる場合でも **Phase 1 完了時点までには必ず全ツールを稼働状態にする**

## Alternatives Considered（検討した代替案）

| 候補 | 概要 | 採用しなかった理由 |
|---|---|---|
| **Phase 0 で全部入れる** | 初期セットアップ時に全ツール稼働 | （採用） |
| MVP では入れず、必要になってから個別追加 | YAGNI を素直に適用 | コミット履歴は遡及修正不可（commitlint）、蓄積した未使用コードの削除可否判断は時間消費が大きい（Knip）、バージョンずれの一括修正は動作リスク（syncpack）。**「後で直す」コストが線形〜超線形に膨張** |
| 段階導入（lefthook と commitlint のみ Phase 0、Knip / syncpack は後） | 折衷案 | コミット履歴規約は救えるが、Knip / syncpack を遅延させた場合の整地コストは結局発生する。半端な導入で「全ツール揃った状態の運用ルール」が固まらない |
| 強制せず、開発者の自主性に任せる | 縛りを最小化 | 個人プロジェクトでも一貫性が崩れる。CI で機械的に弾く方が認知負荷が低い |

## Consequences（結果・トレードオフ）

### 得られるもの
- **規約違反コードの蓄積防止**：CI / フックで違反を即座に弾く
- **コミット履歴の一貫性**：Phase 0 から Conventional Commits 規約が効く。リリースノート自動生成 / 変更分類が容易
- **モノレポのバージョン整合性**：syncpack で構造的に保証
- **未使用コードの早期削除**：Knip が PR 時点で検出
- **「途中導入の整地 PR」が発生しない**：レビュー不能な数百ファイル規模の一括修正を回避

### 失うもの・受容するリスク
- **Phase 0 セットアップ時間が増える**（半日程度）
- **CI 実行時間がわずかに延びる**（Knip / syncpack で各 +10 秒程度、許容範囲）
- 一部のツール（Knip 等）はメンテナンスコスト（誤検知の除外設定）が発生する
- **規律が厳しすぎてコミット粒度が荒くなる**懸念は、wip コミットを `chore:` プレフィックスで許容する等の運用で吸収

### 非対称性の重要性（本 ADR の核）

YAGNI 原則は「**遅延しても将来コストが増えない判断**」に適用すべきであり、**「遅延すると将来コストが線形〜超線形に膨張する判断」には適用しない**。本 ADR で扱うツール群は後者に属する。

この非対称性は他の判断軸にも適用できる：

- **観測性のログ必須フィールド・`traceContext`**（→ [ADR 0017](./0017-w3c-trace-context-in-job-payload.md)）：後追加だと過去ログ・進行中ジョブで履歴データが欠損
- **テストフレームワーク選定**：途中変更で既存テスト全件移行が必要
- **PII マスキング方針**：一度漏らした履歴は消せない

→ 本 ADR は「**遅延の不可逆性が高い判断には YAGNI を適用しない**」というメタ方針を確立する役割も持つ。

### 将来の見直しトリガー
- Knip / syncpack の誤検知率が高くなり、メンテナンスコストが導入メリットを上回った場合
- 個別ツールが OSS としてメンテナンス停止した場合（代替ツールへの移行を ADR で記録）
- Biome / TypeScript / Turborepo 側で同等機能が標準提供された場合（重複排除を検討）

## References

- [06-dev-workflow.md: コード品質ツール](../requirements/2-foundation/06-dev-workflow.md#コード品質ツール)
- [CLAUDE.md: 設計原則](../../.claude/CLAUDE.md)
- [ADR 0012: モノレポツールに Turborepo + pnpm workspaces を採用](./0012-turborepo-pnpm-monorepo.md)
- [ADR 0013: コード品質ツールに Biome を採用](./0013-biome-for-tooling.md)
- [ADR 0017: W3C Trace Context をジョブペイロードに埋め込む](./0017-w3c-trace-context-in-job-payload.md)（同じ「遅延すると将来コストが膨張する判断」の例）
- [Conventional Commits](https://www.conventionalcommits.org/)
