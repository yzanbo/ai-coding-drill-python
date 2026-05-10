# R0 セットアップ手順

> **このディレクトリの守備範囲**：[01-roadmap.md](../01-roadmap.md) の R0（基盤立ち上げ）の**詳細手順**を、フェーズごとに 1 ファイル単位で分割して保持する。各ファイル内の手順は **そのファイル独立の 1, 2, 3 ... 連番**で記述し、ファイル間で番号は連動しない（あるファイルの手順を増減しても他ファイル / roadmap には影響しない）。
> **R0 のバックログ概要・進捗状態**は [01-roadmap.md: Now：R0 基盤](../01-roadmap.md#nowr0-基盤直列初期慣行--言語別環境構築) を参照。本ディレクトリは「手順詳細・コマンド・完了基準・トラブルシューティング」を扱う。

---

## 構造と進行順

R0 は 4 フェーズ構成。**01〜03 は直列**で進める（フェーズ内も基本直列、根拠は [ADR 0021](../../../adr/0021-r0-tooling-discipline.md)）。**04（Go 環境構築）の着手タイミングは柔軟**：他 3 つと並行・後続どちらでもよく、LLM プロバイダ抽象化フェーズまでに完了していればよい。

| フェーズ | 状態 | 詳細手順 |
|---|---|---|
| 1. 初期慣行の構築（言語非依存）| ✅ 完了 | [01-foundation.md](./01-foundation.md) |
| 2. Python 環境構築 | 🔴 未着手 | [02-python.md](./02-python.md) |
| 3. Next.js 環境構築 | 🔴 未着手 | [03-nextjs.md](./03-nextjs.md) |
| 4. Go 環境構築（着手タイミング柔軟）| 🔴 未着手 | [04-go.md](./04-go.md) |

**完了マイルストーン**：

- 01-foundation.md 完了（達成済）：commit / lefthook / mise / GitHub Actions / Dependabot 雛形が揃う
- 02-python.md 完了：apps/api が DB + 品質ゲート（pre-commit + pre-push）+ CI 付きで動く
- 03-nextjs.md 完了：apps/web が品質ゲート（pre-commit + pre-push）+ CI 付きで動く
- 04-go.md 完了：apps/workers/grading が品質ゲート + サンドボックス雛形 + CI 付きで動く
- R0 全完了：`docker compose up && mise run api:dev && mise run web:dev && mise run worker:grading:dev` で開発環境が全言語で立ち上がる

---

## 言語別環境構築の構造

Python / Next.js / Go は同じ **環境構築 + 品質ゲート 5 ステップ** パターンで進める：

```
[環境構築（複数ステップに分解）]
  - mise install <ランタイム>      # mise.toml の pin を実体化
  - apps/<name>/ の workspace 初期化 + アプリ雛形 + 静的検査ツールのインストール
  - （Python のみ）DB 基盤 = Docker Compose + ORM + マイグレーション
  - （Go のみ）サンドボックスイメージ Dockerfile スケルトン

[品質ゲート 5 ステップ]
  - mise.toml に <name>:* タスク追記
  - lefthook.yml に <name> 用 pre-commit 追加（静的検査：lint / format / typecheck / knip）
  - lefthook.yml に <name> 用 pre-push 追加（動的検証：テスト / ビルド）
  - GitHub Actions に <name> ジョブ追加（ci-success の needs: に追加）
  - dependabot.yml の対応エコシステムのコメントアウトを解除
```

**hook 役割分担の原則**：

- **pre-commit**：静的検査のみ（速度許容 < 10 秒目安）。ruff / pyright / biome / tsc / knip / gofmt / golangci-lint
- **pre-push**：動的検証（テスト・ビルド、10〜60 秒許容）。pytest / vitest / next build / go test。DB 依存は `pg_isready` で graceful skip
- **CI**：上記すべて + 依存衛生（pip-audit / deptry / syncpack / govulncheck）。最終再保険

---

## R0 で着手しないツール（後続フェーズ待ち）

R0 では着手せず、後続フェーズで導入する項目：

- Pydantic から JSON Schema 出力（Worker 向け）+ FastAPI OpenAPI 3.1（Frontend 向け型生成） — 型同期パイプライン構築フェーズ（最初のスキーマ投入時。雛形だけ R0 で用意可。→ [ADR 0006](../../../adr/0006-json-schema-as-single-source-of-truth.md)）
- pytest / Vitest / Playwright のテスト本格運用 — テスト対象コード待ち（→ [ADR 0038](../../../adr/0038-test-frameworks.md)）
- ミューテーションテスト — R2 以降
- Docker build → ECR push / Terraform — R5

---

## 関連

- 上位：[01-roadmap.md](../01-roadmap.md) — R0 全体のバックログ概要 + R1 以降のリリース計画
- 設計判断：[ADR 0021](../../../adr/0021-r0-tooling-discipline.md) — 補完ツールを R0 から導入する根拠
- 技術選定 SSoT：[2-foundation/06-dev-workflow.md](../../2-foundation/06-dev-workflow.md) — 各ツールの採用根拠と機械強制設定
