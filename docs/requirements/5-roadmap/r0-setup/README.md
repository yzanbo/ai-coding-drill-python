# R0 セットアップ手順

> **このディレクトリの守備範囲**：[01-roadmap.md](../01-roadmap.md) の R0（基盤立ち上げ）の**詳細手順**を、フェーズごとに 1 ファイル単位で分割して保持する。各ファイル内の手順は **そのファイル独立の 1, 2, 3 ... 連番**で記述し、ファイル間で番号は連動しない（あるファイルの手順を増減しても他ファイル / roadmap には影響しない）。
> **R0 のバックログ概要・進捗状態**は [01-roadmap.md: Now：R0 基盤](../01-roadmap.md#nowr0-基盤直列初期慣行--言語別環境構築) を参照。本ディレクトリは「手順詳細・コマンド・完了基準・トラブルシューティング」を扱う。
>
> **本ファイル（README）の役割**：個別フェーズファイル（同ディレクトリ配下の `NN-<phase>.md`）には書ききれない**言語横断のメタ案内**に絞る。具体的には (1) 言語別フェーズ共通の「環境構築 + 品質ゲート 5 ステップ」パターン / (2) hook 役割分担（pre-commit / pre-push / CI）の原則、の 2 点を扱う。個別フェーズ固有の手順は各フェーズファイルが SSoT、進行順序・進捗状態・R0 で着手しない項目は [01-roadmap.md](../01-roadmap.md) が SSoT。

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
- **pre-push**：動的検証（テスト・ビルド、10〜60 秒許容）。pytest / vitest / next build / go test。DB 依存テストは DB 未起動なら **block 方針**（fail させて push をブロック、`docker compose up -d` 後に再 push する運用、graceful skip は採用しない）
- **CI**：上記すべて + 依存衛生（pip-audit / deptry / syncpack / govulncheck）。最終再保険

---

## 編集ルール

**フェーズ番号やファイル名が変わっても他ファイルの編集が不要になる書き方をする**。連番・ファイル名を変えただけで複数ファイルの書き換えが発生する運用は追従漏れの温床になるため、プロース中では番号・固有ファイル名を直接書かず、相対的・抽象的な表現を使う。

- ❌ 番号・固有ファイル名をプロース中に裸書き：「01 で導入する」「01〜04 全フェーズに適用」「02-python.md と同じパターン」「step 3 の手順」
- ✅ 相対的・抽象的な表現：「本フェーズで導入する」「r0-setup 配下の全フェーズに適用」「Python フェーズと同じパターン」「以降の言語別フェーズ」「同ディレクトリ配下の `NN-<phase>.md`」
- Markdown リンク（`[label](./path)`）はファイル名がパス部分に現れるが、リネーム時は grep / IDE で機械的に追従できるので可

---

## 関連

- 上位：[01-roadmap.md](../01-roadmap.md) — R0 全体のバックログ概要 + R1 以降のリリース計画
- 設計判断：[ADR 0021](../../../adr/0021-r0-tooling-discipline.md) — 補完ツールを R0 から導入する根拠
- 技術選定 SSoT：[2-foundation/06-dev-workflow.md](../../2-foundation/06-dev-workflow.md) — 各ツールの採用根拠と機械強制設定
