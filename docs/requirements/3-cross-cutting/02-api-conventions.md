# 02. API 共通仕様

> **このドキュメントの守備範囲**：API 全体の基本方針、認証・セッションの仕組み、エラーフォーマット、ステータスコード方針、レート制限方針、非同期 API のクライアント実装パターン、ヘルスチェック・運用エンドポイント、OpenAPI 自動生成方針。
> **個別エンドポイントの詳細（リクエスト/レスポンス例・受け入れ条件）** は [features/](../4-features/) を参照。
> **機械可読の最新仕様** は OpenAPI（`/api/docs/openapi.json`）が SSoT。本ドキュメントは設計意図と共通方針を残す位置づけ。
> **データ構造**は [01-data-model.md](./01-data-model.md)、**コンポーネント責務**は [02-architecture.md](../2-foundation/02-architecture.md) を参照。

---

## 基本方針

- REST 風 JSON API
- バージョン管理：URL に含めない、Breaking Change は `Accept` ヘッダで分岐するか新エンドポイントを生やす
- 文字コード UTF-8、Content-Type は `application/json`
- 認証：Cookie ベースのセッション（HttpOnly + Secure + SameSite=Lax）
- 全ルートはデフォルト認証必須、`@Public()` デコレータで例外的に認証スキップ（→ [.claude/rules/backend.md](../../../.claude/rules/backend.md)）

---

## OpenAPI 自動生成

- 実装コードから OpenAPI ドキュメントを **自動生成**（採用ライブラリは [05-runtime-stack.md: バックエンド API](../2-foundation/05-runtime-stack.md#バックエンド-apinestjs--typescript) を参照）
- 生成された OpenAPI JSON を `/api/docs/openapi.json` で配信
- Swagger UI を `/api/docs` で配信（開発・ステージング環境のみ）
- 本ドキュメント（09）は **設計意図・共通方針** を残す位置づけで、最新の機械可読仕様は OpenAPI に従う
- 個別エンドポイントの詳細は **[features/](../4-features/) が SSoT**（受け入れ条件・画面動作と直結する記述）

---

## 認証・セッション

### セッションの仕組み

- セッション ID は HttpOnly Cookie に格納（XSS 経由で読めない）
- Cookie 属性：`HttpOnly` + `Secure` + `SameSite=Lax`
- セッション本体は **Redis**（TTL 7 日、操作のたびに延長）
- ログアウト時はサーバ側で Redis のセッションエントリを削除

### 認証要否の制御

- グローバルガード（`APP_GUARD`）でデフォルト認証必須
- 例外（OAuth コールバック等）は `@Public()` デコレータで個別に解除
- 認証フロー詳細は [F-01](../4-features/F-01-github-oauth-auth.md) を参照

---

## エラーフォーマット（RFC 7807 Problem Details に準拠）

すべてのエラーは以下の形式で返す：

```json
{
  "type": "https://example.com/errors/validation",
  "title": "Validation Failed",
  "status": 400,
  "detail": "code must not exceed 64KB",
  "instance": "/submissions",
  "errors": [
    { "field": "code", "message": "Too large" }
  ]
}
```

- `type`：エラー種別の URI（ドキュメントへのリンクが望ましい）
- `title`：人間可読の短い説明
- `status`：HTTP ステータスコード
- `detail`：このリクエスト固有の詳細
- `instance`：エラーが発生したパス
- `errors`：バリデーションエラー時のフィールド別詳細（任意）

---

## ステータスコード方針

| コード | 用途 |
|---|---|
| 200 | 正常完了（同期処理） |
| 202 | 非同期受付（採点・生成ジョブ） |
| 400 | バリデーションエラー |
| 401 | 未認証 |
| 403 | 認証済みだが権限なし |
| 404 | リソースなし |
| 409 | 状態競合（重複送信等） |
| 429 | レート制限超過 |
| 500 | サーバ内部エラー |
| 503 | 一時的に利用不可（DB ダウン等） |

- 401 と 403 を厳密に分ける：未認証なら 401、認証済みでも自分のリソースでないなら 403
- 採点・生成のような非同期 API では 202 を返してジョブ ID を払い出す

---

## レート制限

採用方式・実装ライブラリは [01-non-functional.md: セキュリティ](../2-foundation/01-non-functional.md#セキュリティ最重要) と [05-runtime-stack.md: キャッシュ / セッション](../2-foundation/05-runtime-stack.md#キャッシュ--セッション) を参照。

### 機能別の閾値

| エンドポイント分類 | 制限 |
|---|---|
| `POST /problems/generate`（[F-02](../4-features/F-02-problem-generation.md)） | 1 ユーザー / 1 分 / 5 回 |
| `POST /submissions`（[F-04](../4-features/F-04-auto-grading.md)） | 1 ユーザー / 1 分 / 30 回 |
| `GET /*`（読み取り全般） | 1 IP / 1 分 / 300 回 |

超過時は 429 + RFC 7807 形式で `detail` にリトライ可能時刻を含める。閾値は運用データを見て調整可能。

---

## 非同期 API のクライアント実装方針

採点・生成は非同期。クライアントは以下の流れで結果を取得する：

1. `POST` で受付 → `202 Accepted` + ID（`requestId` / `submissionId`）を取得
2. `GET /<resource>/:id` をポーリング（1〜2 秒間隔、指数バックオフ。クライアント側ライブラリは [05-runtime-stack.md: フロントエンド](../2-foundation/05-runtime-stack.md#フロントエンド) を参照）
3. `status === 'graded' | 'completed'` になったら停止

ジョブの内部フロー（NestJS → Postgres → Go ワーカー → サンドボックス）は [02-architecture.md: 1 ジョブが流れる完全な経路](../2-foundation/02-architecture.md#1-ジョブが流れる完全な経路) を参照。

ジョブ全体を通じた `trace_id` の連結は [ADR 0017](../../adr/0017-w3c-trace-context-in-job-payload.md) を参照。

---

## ヘルスチェック・運用エンドポイント

| メソッド | パス | 用途 |
|---|---|---|
| GET | `/healthz` | Liveness（プロセス生存確認） |
| GET | `/readyz` | Readiness（DB / Redis 接続確認、依存先がすべて健全な場合のみ 200） |

- ECS / Kubernetes 等のオーケストレータがこれらを叩いてコンテナの再起動・配信開始を判断する
- `/readyz` は依存先（Postgres / Redis / 必要に応じて LLM プロバイダ）の到達性を確認する
- 観測ダッシュボードでの監視対象（→ [04-observability.md: ヘルスチェック](../2-foundation/04-observability.md#ヘルスチェック)）

---

## 機能別エンドポイント一覧

エンドポイントの **詳細仕様（リクエスト/レスポンス例・バリデーション・受け入れ条件）** は [features/](../4-features/) が SSoT。本一覧は俯瞰用：

| 機能 | エンドポイント例 |
|---|---|
| [F-01: GitHub OAuth ログイン](../4-features/F-01-github-oauth-auth.md) | `/auth/github`, `/auth/github/callback`, `/auth/logout`, `/auth/me` |
| [F-02: 問題生成リクエスト](../4-features/F-02-problem-generation.md) | `/problems/generate`, `/problems/generate/:requestId` |
| [F-03: 問題表示・解答入力](../4-features/F-03-problem-display-and-answer.md) | `/problems`, `/problems/:id` |
| [F-04: 自動採点](../4-features/F-04-auto-grading.md) | `/submissions`, `/submissions/:id` |
| [F-05: 学習履歴・統計](../4-features/F-05-learning-history.md) | `/me/stats`, `/me/weakness` |

機械可読の最新一覧は OpenAPI が SSoT。
