# 0024. package.json の整合性を syncpack で機械強制し、設定は apps/web/ 配下に直接配置する

- **Status**: Accepted（Frontend 用途、Amended by [0033](./0033-backend-language-pivot-to-python.md) / [0036](./0036-frontend-monorepo-pnpm-only.md)）
- **Date**: 2026-05-09 <!-- ADR 0036 拡張により syncpack を `apps/web/` に再配置・ルールセット縮小（multi-workspace 前提のルール 2 件のみ対象消滅） -->
- **Decision-makers**: 神保 陽平

> **Note**：syncpack 採用判断そのものは維持。配置とルールセットを変更：
>
> - **配置**：root の `.syncpackrc.ts` → `apps/web/.syncpackrc.ts`（[ADR 0036](./0036-frontend-monorepo-pnpm-only.md) 拡張により Frontend ツーリングを apps/web 内に閉じる方針）
> - **ルールセット**：multi-workspace 前提のルール 2 件は対象消滅により不採用、単一 package.json でも有効な 3 件は継続採用
>
> | ルール | 旧（root multi-workspace） | 新（apps/web 単一 package.json） | 単一 package.json でも残す意義 |
> |---|---|---|---|
> | `dependencies` / `devDependencies` の重複検知 | ✅ | ✅ 継続採用 | 同一パッケージが両方に書かれると pnpm の解決順・hoisting・bundle 含有判定がぶれ、本番に dev 専用パッケージが混入する事故が起きうる。workspace 数に依存しない事故なので単一 package.json でも価値が落ちない |
> | `package.json` キー順整形 | ✅ | ✅ 継続採用 | 依存追加時の差分ノイズ（追加位置のばらつき）を排除し、PR レビューで「実質変更」と「並び替え」を切り分けられる。Dependabot PR の機械的可読性にも寄与 |
> | semver 範囲指定子 `^` 統一 | ✅ | ✅ 継続採用 | `^` / `~` / 完全固定の混在は「minor を取り込みたいか / patch だけか / 固定か」の意図が読めず、Dependabot の minor/patch 自動取り込み（[ADR 0028](./0028-dependabot-auto-update-policy.md)）と整合しない範囲が紛れ込む。単一ファイル内でも意図統一として有効 |
> | 外部依存の全 workspace 同一バージョン | ✅ | ❌ 対象消滅（apps/web 1 個のみ、比較対象不在） |  |
> | 内部 workspace パッケージ `workspace:*` 固定 | ✅ | ❌ 対象消滅（内部 pkg 不在） |  |
>
> **再拡張の余地**：将来 `apps/web/` 内部が multi-package 構成（例：`apps/web/packages/ui` + `apps/web/packages/app` のような UI ライブラリ分離 / Storybook 独立等）に拡張された場合、上記の 2 ルール（同一バージョン / `workspace:*`）も apps/web 内で復活させる判断は妥当。
>
> 本文の規約詳細は移行軌跡 + 再拡張時の参考情報として保持する。SSoT は apps/web 着手時に投入する `apps/web/.syncpackrc.ts` に移る。

## Context（背景・課題）

pnpm workspaces + Turborepo によるモノレポ構成では `package.json` がワークスペースごとに分散する（[ADR 0023](./0023-turborepo-pnpm-monorepo.md)）。これにより以下の事故が**蓄積的・気付かれにくく**発生する：

1. **同一パッケージのバージョン不一致**：例えば `apps/web` は `react@18.2.0`、`apps/api` は `react@17.0.2` のように workspace 間で版がずれる。bundle 重複・型不整合・ESM/CJS 分裂が後から顕在化する
2. **dev / prod の重複登録**：同じパッケージが `dependencies` と `devDependencies` の両方に書かれ、解決順次第で挙動がぶれる
3. **semver 範囲指定子の揺れ**：`^5.4.0` / `~5.4.0` / `5.4.0` が混在し、「マイナー更新を取り込みたいか / パッチだけか / 完全固定か」の意図が読み取れない
4. **内部 workspace パッケージ参照のぶれ**：`@ai-coding-drill/shared-types` への参照で `workspace:*` を使うべきところで `*` 等になっており、外部 npm レジストリへの誤解決でビルドが壊れる

これらは `pnpm install` レベルでは検知されず、ランタイム / ビルド時に顕在化する。**気付いた時には数十箇所**になっていることが多く、一括修正は依存解決の連鎖で動作リスクを伴う。

R0 ロードマップ（apps/web 内 Frontend ツーリング整備）の意図は「**パッケージ複数化前に整合性ゲート**」。ワークスペースが少なく違反対象がほぼ無い段階でツールを入れることで、後から累積した違反を一括修正する不可逆コストを回避する（[ADR 0021: 補完ツールを R0 から導入](./0021-r0-tooling-discipline.md) の系譜）。

## Decision（決定内容）

- **`syncpack`（Frontend 用途）を採用**し、`package.json` の整合性ゲートを機械強制する
- **設定ファイルは `apps/web/.syncpackrc.ts` に直接配置**する（Frontend 単一 app 化（→ [ADR 0036](./0036-frontend-monorepo-pnpm-only.md)）に伴い、root 直接配置から apps/web 配下へ移動）。`packages/config/` 配下に共有 base ファイルを置く 2 段構成は採用しない（`packages/config/` 自体が ADR 0036 で廃止）
- **設定形式は TypeScript（`.ts`）**：`syncpack` の `RcFile` 型を import して typo を保存時に弾き、`//` コメントで規約の「なぜ」をインラインに残す（→ [ADR 0022](./0022-config-file-format-priority.md) Tier 3-1）
- **ルールセットは縮小版 3 件**（重複検知 / キー順整形 / `^` 統一）。multi-workspace 前提の 2 件は対象消滅により不採用 → 詳細は冒頭 Note の表を参照
- 将来 apps/web 内が multi-package 構成に拡張された場合のみ、対象消滅した 2 ルール（同一バージョン / `workspace:*`）の再導入を検討する

**運用詳細（機械強制ポリシー表 / 自動修正の運用 / ルール追加・変更時の手順）の SSoT は [06-dev-workflow.md: モノレポ依存整合性（syncpack ルールセット）](../requirements/2-foundation/06-dev-workflow.md#モノレポ依存整合性syncpack-ルールセット) を参照**（運用ルール型 ADR、→ [`.claude/rules/docs-rules.md` §2](../../.claude/rules/docs-rules.md)）。lefthook / CI 接続の対応表は [06-dev-workflow.md: フック × チェック × CI 対応表](../requirements/2-foundation/06-dev-workflow.md#フック--チェック--ci-対応表) 側にある。本 ADR は採用根拠（§Why）と代替案（§Alternatives Considered）を扱う。

設定形式に `.ts` を選んだ理由は [ADR 0022](./0022-config-file-format-priority.md) の Tier 3-1（型 export ありで typo を保存時に弾ける）に従う。代替形式（`.cjs` / `.mjs` / `.yaml` / `.json`）の検討と不採用理由は §Alternatives Considered の表を参照。


## Why（採用理由）

### syncpack を選ぶ理由

- pnpm workspaces / Turborepo に**ネイティブ対応**しており、追加の glue コードが不要
- 設定 1 ファイル（`.syncpackrc.ts`）で完結、ポータビリティが高い
- `versionGroups` / `semverGroups` という宣言的 DSL で「**意図**」が読み取れる
- 検出（`lint`）と修正（`fix-mismatches` / `format`）の責任分離があり、CI / lefthook で使い分け可能
- 補完的な役割：[ADR 0028](./0028-dependabot-auto-update-policy.md) の Dependabot は「外の世界に新版が出た」を検知し PR を作るのに対し、syncpack は「モノレポ内の `package.json` 群が整合しているか」を検証する。役割が衝突しない

### 最小限ルールセットから始める理由（厳格版を採らない理由）

- **R0 「整合性ゲート」方針との整合**：「破られると落ちる最低ライン」であり、最初から厳格にする宣言ではない
- **YAGNI**：`peerDependencies` 整合検証 / banned リスト / workspace 別例外ルール等は、現状使われない構造への先取り。経験ベースのルールは「先取りで作ったルール」より定着しやすい
- **遅延の不可逆性が低い**：[ADR 0021](./0021-r0-tooling-discipline.md) のメタ方針「**遅延の不可逆性が高い判断には YAGNI を適用しない**」は **ツール導入** レベルでの早期化を要求するもので、**個別ルールの追加** は遅延が可能（後から `.syncpackrc.ts` を編集すれば即時適用される）

### `^` 統一を選ぶ理由

- minor / patch を許容することで、Dependabot の minor / patch 自動取り込み（[ADR 0028](./0028-dependabot-auto-update-policy.md)）と一貫
- 完全固定（exact pin）は `pnpm-lock.yaml` で実現できるため二重管理になる
- `~`（patch のみ）は脆弱性 minor 修正の取り込みが緩い

### lefthook pre-commit に lint を接続する理由

- **フィードバックループの短縮**：CI 待ち（30〜60 秒）→ commit 直後（1 秒未満）に違反検知
- **違反 commit を main 履歴に積まない**：pre-commit でブロックされるため、push 後の修正 commit が不要
- **`glob: "package.json"` で対象を絞る**：通常のコード編集 commit には影響せず、依存追加・版変更などの「違反を入れる/触る瞬間」だけ起動する
- **既存 hook との一貫性**：biome / typecheck も glob 付きで pre-commit 接続済みであり、syncpack だけを CI 専用にする合理的根拠が薄かった

### 自動 fix を pre-commit で走らせない理由

- `package.json` の自動書き換えは `pnpm install` のトリガーにもなり得るため、人間がコミット前に明示的に走らせる運用が安全
- 自動修正は `mise run web:syncpack` を開発者が手動実行する半自動運用を維持。lint で検知 → 手動 fix → 再 commit のループが安全側に倒した運用

### なぜ apps/web 直接配置か（`packages/config/` を経由しない・root に置かない）

1. **Frontend ツーリングを apps/web 内に閉じる方針と整合**
   - [ADR 0036](./0036-frontend-monorepo-pnpm-only.md) 拡張で Biome / Knip / tsconfig も apps/web 配下に集約された。syncpack だけ root に残すと「Frontend 設定の物理位置が散る」非対称が生じる
   - syncpack は対象 package.json と同階層に置けば `--config` フラグ不要で発見される
2. **YAGNI**
   - `packages/config/` 配下に共有 base を切り出す 2 段構成は、消費者が apps/web 単一に集中するため indirection の便益がない（さらに `packages/config/` 自体が ADR 0036 で廃止）
3. **役割が見えやすい**
   - 規則が `apps/web/.syncpackrc.ts` に直接書かれていれば、新規参画者が 1 ファイルを読むだけで対象範囲（apps/web 配下の `package.json` 群）と規約を把握できる
4. **Biome / tsconfig との対称構造**
   - apps/web 配下に Frontend 設定が並ぶ統一感が出て、root には言語非依存の設定（`mise.toml` / `lefthook.yml` / `commitlint.config.mjs`）だけが残る

## Alternatives Considered（検討した代替案）

| 候補 | 概要 | 採用しなかった理由 |
|---|---|---|
| A. **syncpack（採用）** | モノレポ向け package.json 整合性リンタ | 設定が宣言的、Dependabot との役割補完、pnpm/Turborepo 対応 |
| B. 手動運用（PR レビュー時の目視確認） | 規約を README に書いて運用 | 機械強制が無いと累積する。[ADR 0021](./0021-r0-tooling-discipline.md) の「補完ツールは R0 から」と矛盾 |
| C. `npm-check-updates` (`ncu`) | 全依存を最新へ一括更新 | 役割が異なる（更新は Dependabot 担当）。整合性検証機能がない |
| D. 自前スクリプト（Node スクリプトで `package.json` をスキャン） | カスタム実装 | 既存ツールで足りる。保守コストが発生 |
| E. Renovate の `packageRules` でグループ化のみ | Renovate は強力だがメイン用途は更新 | [ADR 0028](./0028-dependabot-auto-update-policy.md) で Dependabot を採用済み。整合性検証は別レイヤー |

### 設定ファイル形式の代替案

| 候補 | 採用しなかった理由 |
|---|---|
| `.syncpackrc.json`（純 JSON） | コメント書けず規約の「なぜ」をインラインで残せない |
| `.syncpackrc.json`（JSONC、`//` コメント有り） | syncpack の JSON ローダが許容せず、黙ってデフォルト設定にフォールバック（実機検証） |
| `.syncpackrc.jsonc` | cosmiconfig が `.jsonc` 拡張子を認識しない（実機検証） |
| `.syncpackrc.yaml` | コメント書けるがデータ純度の利点に対し、本リポジトリの TS 主体構成と表記体系が揃わない。型安全もない |
| `.syncpackrc.cjs` / `.mjs` | コメント書けて syncpack も認識するが、型安全がなく typo を実行時まで検知できない |
| **`.syncpackrc.ts`（採用）** | TS の `RcFile` 型を import することでフィールド名・リテラル値の typo を config 書き時点で検知、コメントも書け、リポジトリの TS 主体構成と一貫（実機で syncpack v15 が直接ロードすることを確認済み） |

### 規約セットの代替案

| 候補 | 採用しなかった理由 |
|---|---|
| 厳格版（peer / banned / exact pin / sortFirst / workspace 別例外を全部入れる） | YAGNI。現状必要のないルールを先取りで作ると、規約と現実の対応関係が失われる |
| **最小限版（採用）** | 整合性ゲートとして最低限を機械強制し、必要に応じて追加していく |

## Consequences（結果・トレードオフ）

### 得られるもの

- **モノレポ内 `package.json` の整合性が機械保証**される（version 揃え / 範囲指定子統一 / workspace:* 強制 / dep 重複検知）
- ワークスペース増加時の「累積した不整合の一括修正」コストを構造的に回避
- 開発者間の規約意識を `.syncpackrc.ts` で SSoT 化、人間記憶への依存を排除
- Dependabot の自動 PR がポリシー違反を起こした場合に、CI が機械的に検知

### 失うもの・受容するリスク

- **Dependabot の自動 PR が syncpack の規約に抵触する可能性**：例えば「同一バージョン揃え」の対象パッケージが片方の workspace にだけ更新 PR で来るとずれる。Dependabot 側のグループ化（[ADR 0028](./0028-dependabot-auto-update-policy.md) の `groups`）で多くは吸収されるが、抜けがあると CI で落ちる。`groups` と `versionGroups` の整合保守が発生
- **規約を増やす際の認知負荷**：新ルール追加時は `.syncpackrc.ts` の更新と関連ドキュメント（CLAUDE.md / 06-dev-workflow.md）の同期が必要
- **CI 実行時間がわずかに増加**：`syncpack lint` ジョブで数秒（無視できる範囲）
- **設定の SSoT が `.syncpackrc.ts` 1 ファイルに集中**：規約変更時はこのファイル + 関連ドキュメント（CLAUDE.md / 06-dev-workflow.md）の同期が必要

### 将来の見直しトリガー

- **Dependabot の自動 PR が syncpack 違反で頻繁に落ちる**：`groups` / `versionGroups` の整合を見直す
- **将来 Frontend に再度複数 package を持つ設計に至った**（peer 依存を含む共有 package 等）：`peerDependencies` の範囲整合検証ルールを追加（R3〜R5 想定）
- **特定パッケージで互換事故が発生した**：banned リスト / exact pin 強制を該当パッケージのみ追加
- **ワークスペース数が 6〜7 個に増えた**：workspace 別例外ルールが必要かを再検討
- **syncpack のルール数が 10 を超えた**：規約が肥大化していないか、本当に必要か棚卸し
- **モノレポを脱却して polyrepo 化する場合**：syncpack 不要になる（このプロジェクトでは想定されない）
- **Renovate / 他ツールに移行する場合**（[ADR 0028](./0028-dependabot-auto-update-policy.md) と連動）
- **glob `"package.json"` が pre-commit ノイズの原因になった場合**：例えば `pnpm-lock.yaml` の自動更新で頻繁に走るようになる等。glob パターンの絞り込みを再検討
- **`mise run web:syncpack` の手動実行が忘れられがちになった場合**：`stage_fixed: true` 付きで自動修正を pre-commit に接続する案を再検討（影響範囲のテストが必要）

## References

- `apps/web/.syncpackrc.ts`：本 ADR の実装（SSoT、apps/web 着手時に投入予定。→ ADR 0036 拡張で root から移動）
- [.github/workflows/ci.yml](../../.github/workflows/ci.yml)：CI 接続（独立 `syncpack` ジョブ）
- [docs/requirements/2-foundation/06-dev-workflow.md](../requirements/2-foundation/06-dev-workflow.md)：補完ツール俯瞰
- [ADR 0036: Frontend ツーリングを apps/web 内に閉じる](./0036-frontend-monorepo-pnpm-only.md)：tooling 設定の現行物理配置方針
- [ADR 0023: Turborepo + pnpm workspaces](./0023-turborepo-pnpm-monorepo.md)
- [ADR 0018: Biome を採用](./0018-biome-for-tooling.md)
- [ADR 0021: 補完ツールを R0 から導入](./0021-r0-tooling-discipline.md)：「遅延すると将来コストが膨張する判断」シリーズの中核例 / メタ方針の確立元
- [ADR 0010: W3C Trace Context をジョブペイロードに埋め込む](./0010-w3c-trace-context-in-job-payload.md)：同シリーズの観測性領域における実例（参考）
- [ADR 0026: GitHub Actions の段階拡張](./0026-github-actions-incremental-scope.md)
- [ADR 0028: Dependabot 自動更新ポリシー](./0028-dependabot-auto-update-policy.md)
- [ADR 0022: 設定ファイル形式の選定方針](./0022-config-file-format-priority.md)：本 ADR の `.ts` 採用判断の根拠
- [syncpack 公式ドキュメント](https://syncpack.dev/)
