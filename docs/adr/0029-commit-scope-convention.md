# 0029. コミット scope 規約（モノレポ領域 + 自動更新用 deps / deps-dev）

- **Status**: Accepted
- **Date**: 2026-05-05
- **Decision-makers**: 神保 陽平

## Context（背景・課題）

このリポジトリは Conventional Commits（`type(scope): subject` 形式）を採用し、commitlint で機械強制している（[ADR 0021](./0021-r0-tooling-discipline.md)）。
モノレポ構成上、`scope` を「変更が及んだ領域」を示す識別子として運用する必要があるが、設計時に以下の論点が出た：

1. **scope の選択肢を自由記述にするか、列挙にするか**
   - 自由記述だと表記揺れ（`web` / `webapp` / `frontend`）が起き、`git log --grep` でのフィルタが効かなくなる
   - 列挙制にすると、新しい領域を増やすときに commitlint 設定を更新する手間が出る

2. **モノレポの「領域」と「依存更新」をどう識別子で区別するか**
   - 領域 scope（`web` / `api` / `worker` / `shared` / `config` / `infra` / `docs` / `db`）はモノレポの作業対象を示す
   - 一方で [ADR 0028](./0028-dependabot-auto-update-policy.md) で導入した Dependabot は `include: scope` 指定により、依存種別から自動的に scope を生成する：
     - production / github-actions → `(deps)`
     - devDependencies → `(deps-dev)`
     - grouped PR → `(deps)` 固定
   - これらを領域 scope と同列の `scope-enum` に登録しないと、Dependabot の自動 PR が commitlint で弾かれて運用が破綻する

3. **scope 定義の SSoT をどこに置くか**
   - 機械強制は `commitlint.config.ts` の `scope-enum`
   - 人間向けの説明は `.claude/CLAUDE.md`（と過去には PR テンプレート等にも書かれがち）
   - 複数箇所に書くと不可避的にずれが生じる

## Decision（決定内容）

**scope は列挙制とし、領域 scope（web / api / worker / shared / config / infra / docs / db）8 種 + 自動更新 scope（deps / deps-dev）2 種の計 10 種を `commitlint.config.ts` の `scope-enum` で機械強制する。`scope-empty` は許容する**（リポジトリ横断の変更で scope 不要なケースのため）。

**運用詳細（type / scope の完全一覧 / 複数領域跨りの書き方 / scope 追加変更時の手順）の SSoT は [06-dev-workflow.md: コミットメッセージ規約](../requirements/2-foundation/06-dev-workflow.md#コミットメッセージ規約) を参照**（運用ルール型 ADR、→ [`.claude/rules/docs-rules.md` §2](../../.claude/rules/docs-rules.md)）。機械強制 SSoT は [`commitlint.config.ts`](../../commitlint.config.ts)。本 ADR は採用根拠（§Why）と代替案（§Alternatives Considered）を扱う。

## Why（採用理由）

### 列挙制を選ぶ理由

- **表記揺れの防止**：`web` / `webapp` / `frontend` のような揺れが構造的に起きない
- **`git log --grep="(api)"` で確実に絞り込める**：機械可読性が一定品質で保証される
- **新規領域追加が自然な「設計判断」になる**：新しい scope を増やすには commitlint 設定を変える必要があり、その時点で「これは本当に独立した領域か？」を一度立ち止まって考える機会になる
- **モノレポ規模が小〜中の本プロジェクトでは、列挙すべき scope が爆発しない**（10 種で十分）

### 領域 scope を 8 種に絞る理由

- **モノレポの物理ディレクトリと一対一対応**：`apps/*` / `packages/*` / `infra/` / `docs/` の各ディレクトリが scope に対応する
- **`db` だけは物理ディレクトリでなく論理領域**：Drizzle スキーマ・マイグレーションは `apps/api` 配下にあるが、DB スキーマ変更は影響範囲が API 単独でないため独立 scope を割り当てる（マイグレーションを伴う変更を後で `git log` で抽出しやすい）
- **`config` はルート直接配置の tooling 設定群と `packages/config/` の両方を含む**：配置方針の詳細は [packages/config/README.md](../../packages/config/README.md) 参照。両方とも `config` scope を使う

### 自動更新 scope を分離して 2 種追加する理由

- **Dependabot の挙動に追従しないと自動 PR が機能しない**：Dependabot は依存種別（production / dev / grouped）から scope を自動決定する。これを許可しないと commitlint で必ず弾かれる
- **`deps` と `deps-dev` の分離は意味がある**：production 依存の更新は本番挙動に影響しうる、devDependencies は開発体験のみに影響、という温度感の違いが scope だけで伝わる
- **人間が手動でコミットする際にも使える**：例えば手動で `pnpm up react` した場合は `build(deps): ...`、手動で `pnpm up -D vitest` した場合は `build(deps-dev): ...` を選べる

### `scope-empty` を許容する理由

- **リポジトリ横断の変更で scope を強制すると違和感が出る**：例えば `chore: lefthook を導入` のような全体に関わる変更で、無理に scope を付けるとミスリードになる
- **CLAUDE.md のリポジトリ規律変更等もこのケース**

### SSoT を `commitlint.config.ts` に置く理由

- **commitlint が CI で検証する唯一の真実**：人間が読む `.claude/CLAUDE.md` は説明用の写しに過ぎない
- **設定ファイルが複数ある場合、機械強制される側を正とする**が原則

## Alternatives Considered（検討した代替案）

| 候補 | 概要 | 採用しなかった理由 |
|---|---|---|
| A. 自由記述 scope（`scope-enum` 撤廃） | 開発者が好きな scope 名を書ける | 表記揺れで `git log` 絞り込みが破綻、scope の意味が個人差で揺れる |
| B. 領域 scope のみ（`deps` / `deps-dev` を含めない） | モノレポ領域だけ列挙 | Dependabot の自動 PR が必ず弾かれて自動更新が機能しない |
| C. **領域 + 自動更新の混在列挙（採用）** | 8 種の領域 + 2 種の自動更新 | 両者を同居させても scope の用途は文脈で識別できる（人間が手で書く時は領域、Dependabot は deps/deps-dev） |
| D. ブランチ名にも scope を強制 | `feature/<scope>/<name>` のように scope をブランチに展開 | 複数領域に跨る変更でブランチ名を選べなくなる。commit 側で `feat(api,worker): ...` のようにカンマ区切りで表現する方が柔軟 |

## Consequences（結果・トレードオフ）

### 得られるもの

- **`git log --grep` での領域別フィルタリング**が機械的に成立
- **Dependabot 自動 PR が commitlint を通過する**：自動更新運用が実用可能
- **新しい領域追加が「ADR 級の判断」として顕在化**：scope を増やす時に立ち止まる仕組みが組み込まれる
- **`deps` / `deps-dev` の分離で依存更新の温度感が `git log` から読み取れる**

### 失うもの・受容するリスク

- **新規 workspace 追加時に `scope-enum` 更新が必要**：例えば将来 `apps/admin` を追加する場合、`admin` scope の追加と CLAUDE.md の表更新が同時に必要。これは「忘れたら commit が弾かれる」ので機械的に検知される
- **Dependabot が将来 scope 命名規則を変えた場合の追従**：例えば `include: scope` の挙動が変更されたり、新しい scope（例：`deps-peer`）が追加された場合、`scope-enum` を更新するまで自動 PR が落ちる
- **Renovate に移行した場合の差異**：Renovate は scope 自動付与の仕組みが Dependabot とは異なるため、再設計が必要（[ADR 0028](./0028-dependabot-auto-update-policy.md) の見直しトリガーと連動）

### 将来の見直しトリガー

- **新規 workspace（`apps/*` / `packages/*`）追加時**：対応する scope を追加
- **Dependabot 仕様変更時**：自動付与される scope に変化があれば追従
- **scope の数が 15 を超えた場合**：列挙制の維持コストが高まるため、グループ化（`apps-*` プレフィックス等）を再検討
- **scope の意味がぶれ始めた場合**（例：`config` がルート設定とパッケージ設定で混在）：`config-root` / `config-pkg` への分割を検討

## References

- [commitlint.config.ts](../../commitlint.config.ts)：本 ADR の機械強制実装（SSoT）
- [.claude/CLAUDE.md](../../.claude/CLAUDE.md)：人間向け scope 表（副 SSoT）
- [.github/dependabot.yml](../../.github/dependabot.yml)：自動 PR が `include: scope` で `deps` / `deps-dev` を生成する設定
- [ADR 0021](./0021-r0-tooling-discipline.md)：commitlint を R0 から導入
- [ADR 0028](./0028-dependabot-auto-update-policy.md)：Dependabot ポリシー（本 ADR の `deps` / `deps-dev` 追加の動機）
- [Conventional Commits 公式](https://www.conventionalcommits.org/)：scope の自由度に関する基準
