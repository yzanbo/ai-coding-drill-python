# 0021. 補完ツール（lefthook / commitlint / Knip / syncpack / ruff / pyright / pip-audit / deptry）を R0 から導入

- **Status**: Accepted
- **Date**: 2026-05-09 <!-- Python pivot（ADR 0033）に追従して Python 側ツール（ruff / pyright / pip-audit）も同じ非対称性論理で R0 採用 -->
- **Decision-makers**: 神保 陽平

## Context（背景・課題）

リポジトリの初期セットアップ時点で、以下の補完ツールを **R0 で導入するか / 必要になるまで遅延するか** を決める必要がある：

**言語横断 / TS（Frontend）側**：

- **lefthook**：Git フック管理（pre-commit / commit-msg、言語横断）
- **commitlint**：Conventional Commits 規約に基づくコミットメッセージ検証（言語横断）
- **Knip**：未使用の export / 依存 / ファイルの検出（TS / Frontend 限定）
- **syncpack**：モノレポ内の `package.json` バージョン整合性強制（TS / Frontend 限定）

**Python（Backend）側**：

- **ruff**：lint + format 違反の検出（→ [ADR 0020](./0020-python-code-quality.md)）
- **pyright**：型ドリフトの検出（→ [ADR 0020](./0020-python-code-quality.md)）
- **pip-audit**：`uv.lock` の脆弱性スキャン（→ [ADR 0035](./0035-uv-for-python-package-management.md)）
- **deptry**：未使用 / 未宣言 / transitive 依存の検出（Knip の dep 検査に対称、→ [ADR 0035](./0035-uv-for-python-package-management.md)）

このプロジェクトの設計原則 ([CLAUDE.md](../../.claude/CLAUDE.md)) は「YAGNI：使うか分からない抽象化を先取りで作らない」を掲げている。これに従えば「必要になってから導入」が自然な選択肢に見える。

しかし上記ツールには、**他の YAGNI 対象（例：抽象化レイヤ・将来の機能要件）と異なる性質**がある：**途中導入時の修正コストが、放置期間に対して線形〜超線形に膨張する**。具体的には：

- **commitlint**：過去のコミット履歴は遡及修正不可。R4 で導入しても、R0〜R3 のコミット履歴は規約外のまま残る
- **Knip**：R4 で導入すると、蓄積した未使用コード・依存を一斉検出することになり、削除可否を個別判断する作業に大きな時間がかかる
- **syncpack**：バージョンずれが積もると、一括修正に動作リスクが伴う（依存関係の互換性を都度検証する必要）
- **lefthook**：自体の途中導入コストは低いが、上記ツールを動かすフックを後から差し込むだけのフレームワークなので、上記と同じく「動かす対象」が積もる前に入れる方が安い
- **ruff**：lint 違反 / format 差分が Python ファイル蓄積後に検出されると、削除可否ではなく「規約違反だがコードとしては正しい」整地が大量発生する。Knip と同じ性質
- **pyright**：型ドリフト（暗黙の `Any` / `Optional` 漏れ / `Mapped[T]` 不在）が積もると、`strict` モード引き上げが事実上不可能になる。「basic で開始 → 後で strict」（[ADR 0020](./0020-python-code-quality.md)）の戦略は R0 導入が前提
- **pip-audit**：脆弱性混入は **Dependabot 待ち時間中に main に入る** リスクがある。Dependabot は更新 PR を提案する側、`pip-audit` は **混入の瞬間に PR を fail-closed する**側で、両者は補完関係（[ADR 0035](./0035-uv-for-python-package-management.md) の二重ゲート方針）
- **deptry**：未使用 / 未宣言 / transitive 依存は積もるほど検出後の整地コストが増える。Knip と同じ「線形膨張」性質で、TS と Python で対称な dependency hygiene ゲートを揃える価値がある

つまり「YAGNI で導入を遅延する」と「将来の修正コストに変換するだけ」になる、という非対称性がある。

なお Biome（TS）は [ADR 0018](./0018-biome-for-tooling.md) で、ruff / pyright（Python）は [ADR 0020](./0020-python-code-quality.md) で、tool 版数管理（mise）は [ADR 0039](./0039-mise-for-task-runner-and-tool-versions.md) で、それぞれ R0 採用が確定済みだが、本 ADR ではそれら**個別ツール選定とは独立に「R0 導入の方針そのもの」**を扱う（メタ方針）。

## Decision（決定内容）

**補完ツール（lefthook / commitlint / Knip / syncpack / ruff / pyright / pip-audit / deptry）を R0（リポジトリ初期セットアップ時）から導入する。**

- 設定の物理配置：本 ADR で扱う補完ツールはすべてリポジトリルート直接配置（`pyproject.toml` の `[tool.*]` セクション含む）。詳細な配置方針は [packages/config/README.md](../../packages/config/README.md) を参照
- **lefthook と CI で多層防御**：lefthook を `--no-verify` で skip された場合も CI が最終 gate になる
- **mise 経由起動で統一**：lefthook フック・CI ジョブとも `mise run <task>` 形式で各ツールを起動する（[ADR 0039](./0039-mise-for-task-runner-and-tool-versions.md)）
- フック × チェック × CI の対応表（どのツールがどのフック・どの CI ジョブで動くか）の SSoT は要件定義書側 [06-dev-workflow.md: フック × チェック × CI 対応表](../requirements/2-foundation/06-dev-workflow.md#フック--チェック--ci-対応表) に集約。本 ADR は採用根拠を扱い、運用上の対応関係はそちらを参照
- 自動修正系（`syncpack fix` / `knip --fix` / `ruff format` の自動書き戻し / `ruff check --fix`）の運用：
  - **pre-commit に接続して安全に書き戻すもの**：Biome の format 差分、ruff format
  - **pre-commit に接続しないもの**：`syncpack fix`（他 workspace の package.json を書き換え）/ `knip --fix`（削除可否は人間レビュー）/ `ruff check --fix`（一部のルールはセマンティクス変更を伴う、手動実行）
  - 手動実行：`mise run sync-fix` / `mise run knip-fix` / `mise run api-lint-fix`
- 導入が遅れる場合でも **Backend / Frontend / Worker の各実装着手時点までには必ず該当言語のツールを稼働状態にする**

## Why（採用理由）

1. **遅延の不可逆性（線形〜超線形の膨張）**
   - commitlint：過去のコミット履歴は遡及修正不可で、後期導入では初期のコミットが規約外のまま固定化される
   - Knip：蓄積した未使用コード・依存の一斉検出は、削除可否を個別判断する作業に大きな時間がかかる
   - syncpack：バージョンずれの一括修正は依存互換性の検証コストを伴う
   - **ruff**：lint 違反 / format 差分の蓄積は「規約違反だがコードとしては正しい」整地を大量発生させる
   - **pyright**：型ドリフト（暗黙の `Any` / `Optional` 漏れ）が積もると `strict` 引き上げが事実上不可能になる
   - **pip-audit**：脆弱性パッケージ混入は Dependabot 待ち時間中に main に入りうる、混入の瞬間にゲートする必要
   - これらは「後で直す」と決めた瞬間に将来コストが線形〜超線形に膨張する性質を持つ
2. **YAGNI 原則の正しい適用範囲を明示**
   - YAGNI は「遅延しても将来コストが増えない判断」に適用すべき原則
   - 本 ADR で扱うツール群は逆の性質（遅延でコスト膨張）のため、YAGNI を適用しない
   - 同様の性質を持つ判断（観測性の `traceContext` → ADR 0010、PII マスキング、テストフレームワーク選定）にも転用できるメタ方針
3. **R0 セットアップコスト（半日程度）が後の整地コストより圧倒的に安い**
   - 後追加の場合、レビュー不能な数百ファイル規模の整地 PR が発生する
   - 個人プロジェクトでもこの整地 PR は破壊的変更や誤検知判断で時間を消費する
4. **CI / フックによる機械的強制が認知負荷を下げる**
   - 「自主性に任せる」と一貫性が崩れ、レビューで人間が品質をチェックすることになる
   - lefthook + commitlint + Knip + syncpack を CI で機械化することで、規律を判断するコストをツールに委譲できる
5. **段階導入（折衷案）より一括導入の方が運用ルールが固まる**
   - 一部だけ R0 で入れると「全ツール揃った状態の運用ルール」が確立されず、後続ツール導入時に再学習コストが発生
   - 一括導入で運用ルールを R0 に集中させる方が総コストは低い
6. **モノレポ規模が小〜中のうちに規律を確立する効果が最大**
   - パッケージ数 5〜10 個のうちに導入すれば誤検知の整地も小規模で済む
   - 本格運用で 8〜12 個に増えてから導入すると整地対象が増える

7. **3 言語ポリグロット構成での運用ルール統一**
   - Python pivot（[ADR 0033](./0033-backend-language-pivot-to-python.md)）以降、本プロジェクトは Backend (Python) / Frontend (TS) / Worker (Go) の 3 言語構成
   - 各言語に「lint+format / 型 / 脆弱性スキャン」の R0 ゲートを揃えることで、**3 言語に対称な品質ゲート**が成立する
   - mise（[ADR 0039](./0039-mise-for-task-runner-and-tool-versions.md)）で起動コマンドが言語横断に統一されるため、運用ルールの認知負荷も最小

## Alternatives Considered（検討した代替案）

| 候補 | 概要 | 採用しなかった理由 |
|---|---|---|
| **R0 で全部入れる** | 初期セットアップ時に全ツール稼働 | （採用） |
| MVP では入れず、必要になってから個別追加 | YAGNI を素直に適用 | コミット履歴は遡及修正不可（commitlint）、蓄積した未使用コードの削除可否判断は時間消費が大きい（Knip）、バージョンずれの一括修正は動作リスク（syncpack）。**「後で直す」コストが線形〜超線形に膨張** |
| 段階導入（lefthook と commitlint のみ R0、Knip / syncpack は後） | 折衷案 | コミット履歴規約は救えるが、Knip / syncpack を遅延させた場合の整地コストは結局発生する。半端な導入で「全ツール揃った状態の運用ルール」が固まらない |
| 強制せず、開発者の自主性に任せる | 縛りを最小化 | 個人プロジェクトでも一貫性が崩れる。CI で機械的に弾く方が認知負荷が低い |

## Consequences（結果・トレードオフ）

### 得られるもの
- **規約違反コードの蓄積防止**：CI / フックで違反を即座に弾く
- **コミット履歴の一貫性**：R0 から Conventional Commits 規約が効く。リリースノート自動生成 / 変更分類が容易
- **モノレポのバージョン整合性**：syncpack で構造的に保証
- **未使用コードの早期削除**：Knip が PR 時点で検出
- **「途中導入の整地 PR」が発生しない**：レビュー不能な数百ファイル規模の一括修正を回避

### 失うもの・受容するリスク
- **R0 セットアップ時間が増える**（半日程度）
- **CI 実行時間がわずかに延びる**（Knip / syncpack で各 +10 秒程度、許容範囲）
- 一部のツール（Knip 等）はメンテナンスコスト（誤検知の除外設定）が発生する
- **規律が厳しすぎてコミット粒度が荒くなる**懸念は、wip コミットを `chore:` プレフィックスで許容する等の運用で吸収

### 非対称性の重要性（本 ADR の核）

YAGNI 原則は「**遅延しても将来コストが増えない判断**」に適用すべきであり、**「遅延すると将来コストが線形〜超線形に膨張する判断」には適用しない**。本 ADR で扱うツール群は後者に属する。

この非対称性は他の判断軸にも適用できる：

- **観測性のログ必須フィールド・`traceContext`**（→ [ADR 0010](./0010-w3c-trace-context-in-job-payload.md)）：後追加だと過去ログ・進行中ジョブで履歴データが欠損
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
- [ADR 0033: バックエンドを Python に pivot](./0033-backend-language-pivot-to-python.md)（Python 側ツールを R0 へ拡張する契機）
- [ADR 0018: TypeScript のコード品質ツールに Biome](./0018-biome-for-tooling.md)（Superseded by 0033、Frontend 用途として継続採用）
- [ADR 0019: Go のコード品質ツール（gofmt + golangci-lint）](./0019-go-code-quality.md)
- [ADR 0020: Python のコード品質ツールに ruff + pyright を採用](./0020-python-code-quality.md)
- [ADR 0035: Python のパッケージ管理に uv を採用（pip-audit 含む）](./0035-uv-for-python-package-management.md)
- [ADR 0036: Frontend モノレポ管理を pnpm workspaces のみに縮小](./0036-frontend-monorepo-pnpm-only.md)
- [ADR 0039: タスクランナー兼 tool 版数管理に mise を採用](./0039-mise-for-task-runner-and-tool-versions.md)
- [ADR 0026: GitHub Actions の段階拡張](./0026-github-actions-incremental-scope.md)（本 ADR の R0 採用ツールを CI 化する対の判断）
- [ADR 0010: W3C Trace Context をジョブペイロードに埋め込む](./0010-w3c-trace-context-in-job-payload.md)（同じ「遅延すると将来コストが膨張する判断」の例）
- [Conventional Commits](https://www.conventionalcommits.org/)
