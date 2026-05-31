# explainers — 非エンジニア向けのしくみ解説

このディレクトリは **非エンジニア（事業側 / 学習者 / 採用面接官など）でも読める**
ように書いた、プロジェクトの主要なしくみの解説集です。

技術仕様の SSoT（Single Source of Truth）は [../docs/requirements/](../docs/requirements/)
と [../docs/adr/](../docs/adr/) です。本ディレクトリは **要件ではなく解説** で、
正式仕様の鏡ではありません。仕様が変わったら本ディレクトリも追従して更新します。

## ファイル一覧

| ファイル | 内容 | 関連する正式仕様 |
|---|---|---|
| [login.md](login.md) | GitHub OAuth ログインのしくみ（state トークン / セッション / CSRF / レート制限） | [../docs/requirements/4-features/authentication.md](../docs/requirements/4-features/authentication.md) |

今後追加予定（例）：

- `grading.md` — 自動採点のしくみ（LLM + サンドボックス）
- `problem-generation.md` — 問題生成のしくみ
- `data-storage.md` — どこに何を保存しているか（Postgres / Redis / S3）

## 書き方の方針

新しい explainer を追加するときは以下を守ってください。

### 読者の前提知識

- HTTP・OAuth・JWT・Redis・Postgres などの **技術用語を初見で理解できない** 想定
- ただし図と例え話で説明されれば概念は追える
- 「サイトの裏で何が起きているか」を **正しいモデル** で把握できることがゴール

### 構成（推奨テンプレ）

1. 登場人物（ブラウザ / サイト / Redis / Postgres / GitHub … など、絵文字で識別）
2. 全体の流れ（ざっくり版、ASCII 図）
3. ステップごとの詳細（必要に応じて）
4. 安全のための見えない仕組み（セキュリティ層）
5. まとめ + もっと詳しく知りたい人への参照リンク（要件 .md と ADR）

### 用語の使い方

- **技術用語は使ってよい**（例：セッション / state トークン / CSRF トークン / レート制限）
- ただし **初出時は 1〜2 行で「何のためのものか」を平易に説明** する
- 図のラベルは技術名（Redis, Postgres, GitHub, etc.）で統一すると読みやすい
- 例え話（宿泊台帳 / 付箋 など）は補助として使い、技術用語の置き換えにはしない

### 図のスタイル

- **ASCII 図** を基本とする（GitHub でそのまま見える、レンダリングに依存しない）
- 登場人物は絵文字で識別（👤 ブラウザ / 🏪 サイト / 📋 Redis / 📚 Postgres / 🏛️ GitHub）
- 流れは **左から右、上から下** の一方向で描く
- Mermaid を使うのは「複雑な状態遷移」や「複数 actor 間の時系列メッセージ交換」だけ

### 命名

- ファイル名は **ケバブケース**（`login.md` / `problem-generation.md`）
- ドメイン単位で 1 ファイル、長くなりすぎたらドメイン内で分割
