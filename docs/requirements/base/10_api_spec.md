# 10. API 仕様

> **このドキュメントの守備範囲**：主要エンドポイント一覧、リクエスト/レスポンス例、認証方式、エラーフォーマット、OpenAPI 自動生成方針。
> **機能の背景**は [02_functional.md](./02_functional.md) を、**コンポーネントの責務**は [04_architecture.md](./04_architecture.md) を、**データ構造**は [09_data_model.md](./09_data_model.md) を参照。

---

## API 全般

### 基本方針
- REST 風 JSON API
- バージョン管理：URL に含めない、Breaking Change は `Accept` ヘッダで分岐するか新エンドポイントを生やす
- すべて `application/json`、文字コード UTF-8
- 認証：Cookie ベースのセッション（HttpOnly + Secure + SameSite=Lax）

### OpenAPI 自動生成
- NestJS の `@nestjs/swagger` で**コードから自動生成**
- 生成された OpenAPI JSON を `/api/docs/openapi.json` で配信
- Swagger UI を `/api/docs` で配信（開発・ステージング環境のみ）
- 本ドキュメント（10）は**主要エンドポイントの設計意図**を残す位置付けで、最新の機械可読仕様は OpenAPI に従う

---

## 認証

### GitHub OAuth
| メソッド | パス | 用途 |
|---|---|---|
| GET | `/auth/github` | OAuth 開始（GitHub へリダイレクト） |
| GET | `/auth/github/callback` | OAuth コールバック、セッション確立 |
| POST | `/auth/logout` | ログアウト（セッション破棄） |
| GET | `/auth/me` | 現在のユーザー情報取得 |

### セッションの仕組み
- セッション ID は HttpOnly Cookie に格納
- セッション本体は Redis（TTL 7 日、操作のたびに延長）

---

## 主要エンドポイント

### 問題

| メソッド | パス | 用途 | 認証 |
|---|---|---|---|
| GET | `/problems` | 問題一覧（カテゴリ・難易度フィルタ可） | 任意 |
| GET | `/problems/:id` | 問題詳細（テストケースの一部はマスク） | 任意 |
| POST | `/problems/generate` | 問題生成リクエスト（非同期、ジョブ ID を返す） | 必須 |
| GET | `/problems/generate/:requestId` | 生成ステータス取得（ポーリング用） | 必須 |

#### 例：`POST /problems/generate`
リクエスト：
```json
{
  "category": "array",
  "difficulty": "easy"
}
```
レスポンス（202 Accepted）：
```json
{
  "requestId": "<uuid>",
  "status": "pending"
}
```

#### 例：`GET /problems/generate/:requestId`
レスポンス：
```json
{
  "requestId": "<uuid>",
  "status": "completed",
  "problemId": "<uuid>"
}
```

---

### 解答（Submissions）

| メソッド | パス | 用途 | 認証 |
|---|---|---|---|
| POST | `/submissions` | 解答送信 → 採点ジョブ投入 | 必須 |
| GET | `/submissions/:id` | 解答 + 採点結果取得（ポーリング用） | 必須 |
| GET | `/submissions` | 自分の解答履歴 | 必須 |

#### 例：`POST /submissions`
リクエスト：
```json
{
  "problemId": "<uuid>",
  "code": "export function solve(n: number) { ... }"
}
```
レスポンス（202 Accepted）：
```json
{
  "submissionId": "<uuid>",
  "status": "pending"
}
```

#### 例：`GET /submissions/:id`（採点完了後）
```json
{
  "id": "<uuid>",
  "problemId": "<uuid>",
  "status": "graded",
  "score": 5,
  "totalCount": 5,
  "result": {
    "passed": true,
    "durationMs": 1340,
    "testResults": [
      { "name": "case1", "passed": true }
    ]
  },
  "gradedAt": "2026-04-25T10:00:00Z"
}
```

---

### 学習履歴・統計

| メソッド | パス | 用途 | 認証 |
|---|---|---|---|
| GET | `/me/stats` | 自分の正答率・カテゴリ別習熟度 | 必須 |
| GET | `/me/weakness` | 弱点カテゴリ集計 | 必須 |

---

### ヘルスチェック・運用

| メソッド | パス | 用途 |
|---|---|---|
| GET | `/healthz` | Liveness（プロセス生存確認） |
| GET | `/readyz` | Readiness（DB / Redis 接続確認） |

---

## エラーフォーマット

すべてのエラーは以下の形式で返す（RFC 7807 Problem Details に準拠）：

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

### ステータスコード方針
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

---

## レート制限

| エンドポイント | 制限 |
|---|---|
| `POST /problems/generate` | 1 ユーザー / 1 分 / 5 回 |
| `POST /submissions` | 1 ユーザー / 1 分 / 30 回 |
| `GET /*` | 1 IP / 1 分 / 300 回 |

実装：Redis ZSET による Sliding Log 方式（`@nestjs/throttler` + Redis ストレージ）。

→ 詳細は [03_non_functional.md](./03_non_functional.md#セキュリティ最重要)

---

## 非同期 API のクライアント実装方針

採点・生成は非同期。クライアントは以下の流れで結果を取得：

1. `POST` で受付 → `202 Accepted` + ID を取得
2. `GET /<resource>/:id` をポーリング（TanStack Query、1〜2 秒間隔、指数バックオフ）
3. `status === 'graded' | 'completed'` で停止

→ 採点ジョブの内部フローは [04_architecture.md: 1 ジョブが流れる完全な経路](./04_architecture.md#1-ジョブが流れる完全な経路)
