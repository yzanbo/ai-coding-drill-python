# app/

FastAPI アプリ本体の置き場。URL の受け口（routers）から、業務ロジック（services）、
DB の形（models）、入出力の形（schemas）、共通部品（core / db / deps / observability）まで、
役割ごとにフォルダを分けている。

各フォルダの役目は、それぞれの README.md を見る。レイヤ全体の規約は
[.claude/rules/backend.md](../../../.claude/rules/backend.md) が SSoT。

| フォルダ | これは何か（役目） |
|---|---|
| [routers/](./routers/README.md) | FastAPI の `APIRouter` で「**どの URL をどの関数で受けるか**」を宣言する**受付係**。入力検証と `Depends` での前処理の取り出しだけ行い、業務処理は services に丸投げする |
| [services/](./services/README.md) | 1 機能の**業務処理本体**（ビジネスロジック / 計算 / 分岐 / 認可チェック / トランザクション境界 / Pydantic 詰め替え）を実装する**実務担当**。routers から呼ばれ、DB アクセスは repositories に委譲し、結果を schemas の形に詰め替えて返す（→ [ADR 0044](../../../docs/adr/0044-backend-repository-pattern-adoption.md)） |
| [repositories/](./repositories/README.md) | **DB アクセスの窓口**。SQLAlchemy クエリの実装だけを集約し、ORM オブジェクトをそのまま返す。services から呼ばれ、ビジネスロジック・Pydantic 変換は持たない（→ [ADR 0044](../../../docs/adr/0044-backend-repository-pattern-adoption.md)） |
| [schemas/](./schemas/README.md) | API 入出力 JSON の「**形**」を **Pydantic クラス**で宣言するフォルダ。**型の正本（SSoT）**で、Frontend の TS 型・Worker の Go 型もここから自動生成される |
| [models/](./models/README.md) | DB テーブルの「**形**」を **SQLAlchemy クラス**で書く**設計図**。Alembic がここを見てマイグレーション SQL を自動生成する。schemas（JSON の形）とは別物 |
| [db/](./db/README.md) | `AsyncEngine`（アプリ全体の接続プール）と `AsyncSession`（1 リクエスト 1 つの会話チャネル）を作る **DB との通信路（出入り口）**。実際の SQL は repositories 側で書く |
| [core/](./core/README.md) | 設定値（`.env`）・ドメイン例外・OAuth クライアントなど、**機能をまたぐ横断ユーティリティ**を置く道具箱。何も他フォルダを import しない終端 |
| [deps/](./deps/README.md) | FastAPI の `Depends(...)` に渡して routers の引数に自動で差し込まれる**部品**（ログイン中ユーザー / DB セッション / レート制限 / ページネーション等）を集める**アダプタ層**。前処理を集約して routers を業務処理に集中させる |
| [observability/](./observability/README.md) | ログ・分散トレース（OpenTelemetry）・メトリクス（Prometheus）の**初期化処理**を置くフォルダ。`main.py` が起動時に 1 回だけ呼ぶ計測装置のセットアップで、業務コードからは触らない |
| `main.py` | FastAPI インスタンスを作り、各 router を `include_router(...)` で束ねる**アプリ起動の入口**。observability の初期化もここで行う |

## レイヤ間の呼び出しの向き

新しい機能を作る時、どのフォルダから どのフォルダを呼んでよいかを下図で固定する。
**矢印の向きにのみ呼び出し可、逆向きは禁止**（循環依存を防ぐため）。

```
                  [リクエスト]
                       │
                       ▼
                  ┌─────────┐                ┌─────────┐
                  │ routers │───────────────►│ schemas │  response_model
                  └────┬────┘                └─────────┘  (返す JSON の形を指定)
              ┌────────┴────────┐
       Depends で取り出す   直接呼び出す
              │                  │
              ▼                  ▼
          ┌──────┐         ┌──────────┐      ┌─────────┐
          │ deps │────────►│ services │─────►│ schemas │  model_validate
          └──┬───┘         └────┬─────┘      └─────────┘  (ORM → schemas
             │                  │                          へ詰め替え)
             │                  ▼
             │           ┌──────────────┐
             │           │ repositories │     SQLAlchemy クエリの実装
             │           └──────┬───────┘
             │                  │
             │              ┌───┴────┐
             │              ▼        ▼
             │           ┌────┐  ┌────────┐
             └──────────►│ db │◄─┤ models │
                         └────┘  └────────┘
              AsyncSession を取得   db.Base を継承
```

> 図中の `schemas` は同じ `app/schemas/` パッケージで、参照タイミングが 2 つあるため 2 箇所に描いている。
> （右上 = routers がレスポンス形を宣言する時、右下 = services が Repository から受け取った ORM オブジェクトを Pydantic に詰め替える時）

図に入りきらない関係（補足）：

- `schemas`：他のレイヤを import しない終端（TS / Go への型生成境界を保つため）
- `core`：どのレイヤからも参照可。何も呼び返さない終端（設定・例外クラス等）
- `observability`：`main.py` が起動時に 1 回だけ初期化。業務コードからは触らない
- `services` と `repositories` の責務分担：Service はビジネスロジック + 認可 + トランザクション境界 + Pydantic 詰め替え、Repository は SQLAlchemy クエリ実装のみ（→ [ADR 0044](../../../docs/adr/0044-backend-repository-pattern-adoption.md)）

### 読み方（具体例）

- **正常な流れ**：ブラウザが `/problems` を叩く → `routers/problems.py` がリクエストを受け取り、
  `services/problems.py` に処理を渡す → services が `repositories/problems.py` の Repository メソッドを呼ぶ
  → Repository が `models/problems.py` で DB からデータを取り ORM オブジェクトを返す
  → services が `schemas/problems.py` の形に詰め替えて返す。
- **`deps/` が間に入る場合（ユーザー取得）**：`Depends(get_current_user)` を routers の引数に書くと、
  deps の内部で DB から引き当てたログイン中ユーザーを routers に渡す。
  呼び出し順は **routers → deps → services → repositories**（逆向き import は禁止）。
- **`deps/` が間に入る場合（DB セッション）**：`Depends(get_async_session)` は services を経由せず、
  deps が `db.session` から直接 `AsyncSession` を yield して routers に渡す。
  services はそれを受け取り、Repository の `__init__` に渡す。
- **`core/` は終端**：設定値（`.env` の中身）や共通例外クラスを置く場所。どこからでも呼んでよいが、
  core から業務フォルダを呼び返してはいけない（呼び返すと循環する）。
- **`observability/` は別系統**：ログやトレースのセットアップで、起動時に 1 回だけ `main.py` から
  呼ばれる。普段の業務コードからは触らない。

### やってはいけないこと（よくある間違い）

- ❌ `routers/` から `models/` / `repositories/` を直接 import（DB アクセスは services 経由、services が Repository を呼ぶ）
- ❌ `services/` から SQLAlchemy を直接呼ぶ（DB クエリは Repository に切り出す、→ [ADR 0044](../../../docs/adr/0044-backend-repository-pattern-adoption.md)）
- ❌ `services/` から `routers/` を import（逆流）
- ❌ `services/` から `deps/` を import（逆流。current_user は routers が `Depends` で取り出して引数に渡す）
- ❌ `repositories/` から `schemas/` / `services/` を import（戻り値は ORM、Pydantic 変換は Service の責務）
- ❌ `schemas/` から `services/` や `models/` を import（schemas は形だけで他に依存しない）
- ❌ A → B かつ B → A の関係（循環）。services 内の機能間（例：`grading` と `submissions`）も同じ

ルールの正本（表形式・コード例付き）は [.claude/rules/backend.md: レイヤ間の import 方向](../../../.claude/rules/backend.md)。
