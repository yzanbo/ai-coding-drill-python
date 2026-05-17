# 0047. セッションストアに Redis を採用（Postgres セッションテーブル / JWT を不採用）

- **Status**: Accepted
- **Date**: 2026-05-17
- **Decision-makers**: 神保

## Context（背景・課題）

[ADR 0005](./0005-redis-not-for-job-queue.md) は「**Redis をジョブキュー用途で使わない**」という禁止判断であり、Redis を **キャッシュ・セッション・レート制限の 3 用途**に限定するとだけ書かれている。一方で「セッション用途で Redis を積極選択した根拠」は記録されていない。

実際に [ADR 0011](./0011-github-oauth-with-extensible-design.md) §Decision には「セッション管理：Cookie ベース（HttpOnly + Secure + SameSite=Lax）、ストレージは Redis（Upstash）、TTL 7 日」と一行で書かれているが、なぜ Postgres セッションテーブルでなく Redis を選んだのか / なぜ JWT（stateless）にしなかったのか / Cookie 属性をなぜ `SameSite=Lax` にしたかの根拠が ADR レベルで残っていない。

セッションストアの選択は **認証アーキテクチャ全体**に影響する：

- **Postgres セッションテーブル**：DB を一系統に集約、認証 1 回ごとに DB ヒット
- **Redis セッション**：認証 1 回ごとに Redis ヒット、Postgres と Redis の 2 系統運用
- **JWT（stateless）**：ストアなし、Cookie or `Authorization` ヘッダーに署名付きトークンを格納

R0-2（GitHub OAuth 実装）の着手前に判断を明文化し、認証コードが「なぜそうなっているか」を読み取れるようにする。

### 関連 ADR

- [ADR 0005](./0005-redis-not-for-job-queue.md) — Redis の用途を 3 つに絞る判断（本 ADR の前提）
- [ADR 0011](./0011-github-oauth-with-extensible-design.md) — GitHub OAuth 採用、Cookie + Redis を 1 行で言及
- [ADR 0012](./0012-upstash-redis-over-elasticache.md) — Redis ホスティングは Upstash
- [ADR 0034](./0034-fastapi-for-backend.md) — Backend は FastAPI

## Decision（決定内容）

**セッションは「サーバサイドストア + 不透明セッション ID Cookie」方式とし、ストアは Redis（Upstash）を採用する**。JWT および Postgres セッションテーブルは採用しない。

### セッション ID Cookie の仕様

| 属性 | 値 | 理由 |
|---|---|---|
| 名前 | **`session_id`** | 自己ドキュメント性を優先（コード・ログ・監査で役割が一目で分かる）。obscurity による技術スタック推測困難化は OWASP の主防御に含まれず、HttpOnly / Secure / SameSite / 不透明値 / CSRF token / 署名で十分（→ §Why の改訂理由） |
| 値 | 32 byte 以上の **CSPRNG ランダム**を base64url 化 + itsdangerous で署名（不透明 ID） | セッションそのものを Cookie に入れない、ストア側で実体を持つ。署名は改ざんを Redis 問い合わせ前に弾く層 |
| `HttpOnly` | true | JavaScript からの読み取り不可（XSS 経由の token 盗難を防ぐ） |
| `Secure` | true | HTTPS でのみ送信、HTTP 経由のリーク防止 |
| `SameSite` | `Lax` | OAuth callback（top-level GET）で Cookie が運ばれる必要があるため `Strict` 不可、`None` は CSRF 余地が広い |
| `Domain` | アプリドメイン | サブドメイン跨ぎは現状不要 |
| `Path` | `/` | 全エンドポイントで利用 |
| `Max-Age` | 7 日（604800 秒）| Redis 側 TTL と一致 |

### Redis に保持するデータ構造

| キー | 型 | 値の中身 | TTL |
|---|---|---|---|
| `session:<session_id>` | hash | `user_id`, `provider`, `created_at`, `last_seen_at`, `csrf_token`, `user_agent_hash`, `ip_hash` | 7 日（最終アクセス時に touch で延長） |
| `user:<user_id>:sessions` | set | そのユーザーのアクティブ `session_id` 一覧（全端末ログアウト用） | 個別 session_id の expire と同期 |

### CSRF 対策

- セッション作成時に `csrf_token`（32 byte CSPRNG）を併せて発行し Redis に保存
- POST/PUT/DELETE/PATCH リクエストでは **double submit cookie** 方式で照合：Frontend は `csrf_token` を別 Cookie or レスポンスから取得し、リクエストヘッダー `X-CSRF-Token` に詰める。Backend は Cookie の `sid` で session を引き、ヘッダーの token と Redis 内の `csrf_token` が一致するか検証
- `SameSite=Lax` は GET の OAuth callback で Cookie が運ばれることを許す。POST は SameSite で送られにくいが double submit cookie を二重防御として併用

### 認証フロー上の責務分担

1. Frontend → `GET /auth/github/login` → Backend が GitHub にリダイレクト
2. GitHub → `GET /auth/github/callback?code=...` → Backend が code を access_token に交換 → ユーザー作成 / 取得 → `session_id` 生成 → Redis に `session:<session_id>` を SET（TTL 7 日）→ `Set-Cookie: session_id=...` で返す
3. 以降のリクエスト → Backend Middleware が Cookie の `session_id` で `GET session:<session_id>` → `user_id` を request.state に詰める → ハンドラで `current_user` として利用
4. ログアウト → Backend が `DEL session:<session_id>` + `SREM user:<user_id>:sessions <session_id>` + `Set-Cookie: session_id=; Max-Age=0`

### やらないこと（YAGNI）

- セッションのスライディング延長は **30 分以上アクセス間隔があった時のみ touch**（毎回 EXPIRE 更新するとコスト・複雑度が増えるため簡略化）
- マルチデバイス同時ログイン管理 UI（個別端末ログアウト）は MVP に含めない
- セッションの IP / User-Agent 強制照合は **記録のみで認可には使わない**（モバイル切替などで誤判定多発）

## Why（採用理由）

### 1. 認証チェックは「全 API リクエストで発生する超高頻度アクセス」

- 1 リクエスト = 1 セッション読み取り。R/W 比率は読み取り 99% / 書き込み 1%（ログイン・ログアウトのみ）
- 数百〜数千 req/min 規模でも Redis 単一インスタンスで余裕、Postgres より明確に有利
- Postgres セッションテーブルは index は効くが「DB 接続枯渇」「LISTEN/NOTIFY との競合」「アプリ DB と同居することで認証障害がアプリ全体に波及」というリスクがある

### 2. Redis ネイティブ TTL で「期限切れの自動削除」

- セッションは TTL（7 日）で勝手に消える必要があるデータ
- Redis：`EXPIRE` をキー単位で持ち、満了で即削除（メモリも解放）
- Postgres：cron で `DELETE FROM sessions WHERE expires_at < now()` を回す必要があり、vacuum / autovacuum コストが発生。さらに `expires_at` index が必要

### 3. 揮発性が許容できるデータ性質

- Redis インスタンスが落ちた場合 → 全ユーザー再ログイン 1 回で済む（致命的データ損失ではない）
- ジョブキュー（→ [ADR 0005](./0005-redis-not-for-job-queue.md)）は **失敗 = 採点結果が消える**ため Postgres 必須だが、セッションは **失敗 = 再ログインで復旧**できる対称的に弱い保証で十分
- この「消えても致命的でない」性質は Upstash 無料枠 / サーバレス Redis（→ [ADR 0012](./0012-upstash-redis-over-elasticache.md)）と整合

### 4. JWT（stateless）の弱点を回避

- **revoke が困難**：ログアウト / アカウント停止 / トークン漏洩時に「即座に無効化」できない（短命 + refresh token の組み合わせで近似はできるが複雑）
- **トークンサイズ大**：JWT は base64 でユーザー情報を埋め込むため Cookie が肥大化、リクエストごとに数百 B のオーバーヘッド
- **署名鍵ローテーション**が辛い：複数バージョンの鍵を並走させる仕組みが必要
- **暗号アルゴリズム選定の落とし穴**：HS256/RS256/none などの誤選択で過去事故が多発（JWT spec の `alg: none` 攻撃等）
- セッション ID 方式は **revoke 即時 = Redis から DEL するだけ**、鍵ローテーションなし、サイズは 32 byte 固定。シンプル

### 5. Cookie + サーバサイドストアは「XSS / CSRF 両方の防御に分かりやすい」

- `HttpOnly` で JavaScript からトークンを盗めない → XSS 対策の基本がフレームワーク非依存で効く
- `SameSite=Lax` + double submit cookie で CSRF を二重防御
- Bearer header に JWT を入れる方式は `localStorage` 経由になりがちで、XSS 経由の盗難リスクが上がる

### 6. Postgres セッションテーブル不採用の積極理由

- セッション読み取りは認証チェック 100% に乗るため、**アプリ DB の接続プール圧迫**を招く（特に async pool は枯渇しやすい）
- 認証障害 = アプリ全体障害になる。Redis に逃がせばアプリ DB は応答性を維持できる
- vacuum / autovacuum 戦略を考えなくて済む（セッション = 高頻度 INSERT/DELETE はテーブル肥大化が起きやすい）

### 7. Cookie 名は obscurity ではなく自己ドキュメント性で選ぶ

過去案では Cookie 名を `sid` 等の非自明な短名にして「アプリ非自明な名前で技術スタック推測を困難化」する根拠を採っていたが、本 ADR では `session_id` 採用に改める：

- **OWASP の主防御モデルでは Cookie 名の obscurity は含まれない**：実際の防御は HttpOnly / Secure / SameSite / 不透明値 / CSRF token / 署名（itsdangerous）で完結している
- **攻撃者は DevTools / curl で Cookie を即座に閲覧可能**：名前を伏せても得られる遅延はほぼゼロ
- **自己ドキュメント性のメリットは継続的**：コードレビュー、トラブルシュート、監査、新規参画者の理解スピードに毎リクエスト効く
- **主要 framework も descriptive 寄り**：Django `sessionid` / Spring `JSESSIONID` / Rails `_<app>_session`。短名は `connect.sid`（Express）等の少数派
- **Settings.session_cookie_name で差し替え可能**：本番環境で別名が必要になっても 1 行で変えられる柔軟性は維持

### 8. `SameSite=Lax` の選定根拠

- `Strict`：top-level GET でも Cookie が送られない条件があり、**GitHub OAuth callback で Cookie が消える**ことがある（実装難）
- `None`：CSRF 余地が広い、`Secure` 必須・第三者 Cookie 規制でブラウザ依存
- `Lax`：top-level GET（リダイレクト含む）には乗り、`POST /form` などのクロスサイト POST には乗らない。OAuth callback 互換 + CSRF 防御のバランスが最適

## Alternatives Considered（検討した代替案）

| 候補 | 概要 | 採用しなかった理由 |
|---|---|---|
| **Cookie + Redis セッション** | セッション ID Cookie、実体は Redis に格納 | （採用） |
| **Cookie + Postgres `sessions` テーブル** | DB を一系統に統合 | 認証チェック全リクエストで DB ヒット、アプリ DB 接続プール圧迫、TTL 自前実装、vacuum コスト |
| **JWT（Cookie 格納）** | stateless、ストア不要 | revoke 困難、token サイズ大、署名鍵ローテーションの運用、`alg` 選定の事故事例多数。「即時無効化」が業務上必要なため不採用 |
| **JWT（`Authorization: Bearer ...` ヘッダー）** | SPA で定番 | `localStorage` 経由になり XSS 経由で盗まれやすい、HttpOnly の防御層を捨てる |
| **暗号化 Cookie（クライアントサイド state、stateless）** | サーバ側状態なし | Cookie サイズ上限 4 KB に当たりやすい、鍵ローテーションが困難、CSRF が一段難しい |
| **NextAuth (Auth.js) のセッション機能を Next.js 側に寄せる** | Frontend 完結 | API が FastAPI 中心の設計（→ [ADR 0011](./0011-github-oauth-with-extensible-design.md)）と矛盾、認証ロジックが分散、Backend の設計力アピールが弱まる |
| **Cookie + In-memory（プロセス内 dict）** | 究極にシンプル | プロセス再起動で全ログアウト、複数 Worker で共有不可、本番デプロイで破綻 |
| **`SameSite=Strict`** | CSRF 完全遮断 | top-level GET（OAuth callback）で Cookie が送られないケースあり、実装難 |
| **`SameSite=None`** | クロスサイト全許可 | CSRF 余地が広い、第三者 Cookie 規制でブラウザ依存、要件にない |

## Consequences（結果・トレードオフ）

### 得られるもの

- 認証チェックが Redis ヒットのみで高速（Postgres 接続プールを圧迫しない）
- revoke 即時（Redis `DEL session:<sid>` で無効化）
- TTL ネイティブ（`EXPIRE` 7 日で自動削除、cron 不要）
- `HttpOnly` + `Secure` + `SameSite=Lax` + double submit cookie で XSS / CSRF を多層防御
- Cookie サイズが小さい（32 byte の不透明 ID）、リクエストオーバーヘッド最小
- アプリ DB と認証ストアの障害分離（Redis 障害で API は動かないが、復旧後は再ログインで継続）
- ユーザー単位の全端末ログアウトが `user:<user_id>:sessions` set で 1 操作

### 失うもの・受容するリスク

- **Redis 障害 = 全ユーザー再ログイン**：Upstash は冗長化されているが、完全停止時はログイン体験が悪化
  - 受容：MVP 規模では十分。SLA 要求が出たら ElastiCache cluster mode への移行検討
- **データストアが Postgres / Redis の 2 系統**：バックアップ・監視対象が増える
  - 受容：Redis 側はキャッシュ・セッション・レート制限の 3 用途で永続性弱、バックアップ不要（→ [ADR 0005](./0005-redis-not-for-job-queue.md)）
- **CSRF 防御が double submit cookie ＋ SameSite の組み合わせ**で、Frontend が CSRF token をヘッダーに詰める実装責務を負う
  - 対策：FastAPI 側で middleware を書き、Frontend は Hey API 生成クライアントに interceptor で組み込み
- **マルチリージョン展開時に Redis レイテンシが影響**：認証チェック全リクエストに乗るためリージョン跨ぎコストが顕在化
  - 受容：MVP は単一リージョン、必要になればリージョン別 Redis にレプリケート

### 将来の見直しトリガー

- **Redis 障害が頻発し SLA を満たせない**：ElastiCache cluster mode への移行、または Postgres セッションテーブルへの fallback 検討
- **多リージョン展開**：リージョン別 Redis or session レプリケーション設計
- **Native Mobile App を追加**：Cookie ベース不可、Bearer token への切替（JWT or opaque token + DB lookup）が必要
- **Upstash 無料枠超過**：ElastiCache か別 Redis ホスティングへ移行（→ [ADR 0012](./0012-upstash-redis-over-elasticache.md)）
- **セッション数が爆増し Redis メモリが上限**：TTL 短縮（7 日 → 1 日）or LRU eviction 設定 or 別ストア検討
- **業務要件で「セッション履歴の長期保管」が必要に**：監査用に Postgres `session_audit` テーブルを別途追加（セッション本体は Redis のまま）

## References

- [ADR 0005](./0005-redis-not-for-job-queue.md) — Redis の用途を 3 つに絞る判断（本 ADR の前提）
- [ADR 0011](./0011-github-oauth-with-extensible-design.md) — GitHub OAuth 採用、Cookie + Redis を初出
- [ADR 0012](./0012-upstash-redis-over-elasticache.md) — Redis ホスティング先（Upstash 無料枠）
- [ADR 0034](./0034-fastapi-for-backend.md) — Backend は FastAPI
- [01-non-functional.md: セキュリティ](../requirements/2-foundation/01-non-functional.md#セキュリティ最重要)
- [05-runtime-stack: キャッシュ / セッション](../requirements/2-foundation/05-runtime-stack.md#キャッシュ--セッション)
- [02-architecture.md: データストア](../requirements/2-foundation/02-architecture.md#データストア)
- [OWASP Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html) — Cookie 属性・session ID の選び方
- [OWASP CSRF Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html) — double submit cookie 方式
