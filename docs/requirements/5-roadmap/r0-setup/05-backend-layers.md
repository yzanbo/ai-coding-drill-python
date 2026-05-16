# 05. Backend レイヤ分割（✅ 完了）

> **守備範囲**：`apps/api/app/` 配下に機能別フラットなレイヤ分割（8 レイヤ + `main.py`）を確定し、各レイヤの責務 + import 方向 + 命名規則を `.claude/rules/backend.md` に「実装契約」として固定する。本フェーズが終わると、R1 以降の Backend 機能実装が「悩まずに迷わずレイヤを選ぶ」状態になる。
> **前提フェーズ**：[Python 環境構築フェーズ](./02-python.md) 完了済（`apps/api/app/main.py` / `core/config.py` / `db/session.py` / `db/base.py` / `models/health_check.py` / `schemas/health.py` / `routers/health.py` / `routers/probes.py` が配置済、Postgres + Alembic の最小マイグレーションが通り、`mise run api:dev` で起動可能、ruff / pyright / pip-audit / deptry がローカル + CI 両方で緑）
> **次フェーズ**：[Frontend レイヤ分割フェーズ](./06-frontend-layers.md)
>
> **本フェーズの位置付け**：[README.md: 言語別 setup の後段](./README.md#言語別-setup-の後段レイヤ分割フェーズ) を参照。言語ツーリングが整った上に、その言語側でプロジェクト固有のレイヤ分割を確定するフェーズで、「悩む余地のない基本構造」とは別物として扱う。
>
> **書き方の方針**：本フェーズは依存ライブラリのインストールを伴わないため、言語別フェーズの「環境構築 + 品質ゲート 5 ステップ」パターンには載らない。代わりに「**決定値の確認 → ディレクトリ作成 → 各レイヤ README → 全体 README → rules ファイルに実装契約として固定**」の構造で進める（Frontend レイヤ分割フェーズと同パターン）。
>
> **本ファイルと `.claude/rules/backend.md` の役割分担**：本ファイルが「**手順 + このフェーズで下す決定**」の SSoT、`backend.md` が「**実装契約（R1 以降の機能実装が読む規約）**」の SSoT。`§決定値` の表（`§A` ツリー / `§C` import 方向 / `§D` 命名規則）は両ファイルに同じ値を書く（本ファイル＝決定の根拠と手順、backend.md＝Claude 自動 load 用の機械可読契約）。一方を更新したら他方も合わせて更新する。

---

## 自律実行ポリシー（Claude が本ファイルを読んで作業する時の前提）

本ファイルは Claude に**そのまま実行を依頼**する想定で書かれている。次の原則を守って、ユーザーに確認を取らずに最後まで進める。

1. **ユーザーに設計上の確認を求めない**：`§決定値` に書かれた選択（8 レイヤ構成 / Repository 不採用 / admin・customer 分割不採用 / Service 単層 / 命名規則 等）は**決定済みで議論しない**。関連 ADR（[ADR 0034](../../../adr/0034-fastapi-for-backend.md) / [ADR 0037](../../../adr/0037-sqlalchemy-alembic-for-database.md) / [ADR 0006](../../../adr/0006-json-schema-as-single-source-of-truth.md) / [ADR 0040](../../../adr/0040-worker-grouping-and-llm-in-worker.md)）は既に消化済みのため、再検討しない。
2. **関連ファイルが本ファイルとズレていたら、関連ファイル側を直す**：以下のファイル群が `§決定値` と違う状態にあれば、本ファイルを真として書き換える。本ファイルを書き換える方向には進まない（本ファイルが SSoT のため）：
   - `apps/api/app/` 配下のフォルダ・README（9 個、§A のツリーに対応）
   - `.claude/rules/backend.md`（Backend 全般の実装契約）
   - `.claude/CLAUDE.md`（「ルールファイルの管理」リストに `backend.md` が列挙されていること）
   - `docs/requirements/5-roadmap/01-roadmap.md`（R0-5 行の状態列とリンク列）
3. **新規ブランチを切ってから作業する**：[CLAUDE.md: ブランチ運用](../../../../.claude/CLAUDE.md#ブランチ運用) に従い、`feature/api/r0-5-backend-layers`（または同等の `feature/api/<名前>`）で作業する。`main` で直接作業しない。
4. **コミット・PR 作成は明示指示があるまで行わない**：[CLAUDE.md: Git 操作の禁止](../../../../.claude/CLAUDE.md#git-操作の禁止) に従い、`git add` / `git commit` / `git push` / PR 作成はユーザーから明示指示が出るまで保留する。ファイル作成・編集は自動で進めてよい。
5. **初期状態のばらつきに対する方針**：
   - 想定フォルダが存在しない → 作る（`__init__.py` + `README.md` を入れる）
   - 想定フォルダが存在し中身が空 → README を入れる
   - 想定フォルダが存在し中身がある（既存の `routers/` `schemas/` `models/` `core/` `db/` 等、02-python.md フェーズで埋まったもの） → 中身を確認して `§決定値` と矛盾する部分のみ書き換える。`02-python.md` 由来の実装ファイル（`config.py` / `session.py` / `base.py` / `health_check.py` / `health.py`（schemas）/ `health.py`（router）/ `probes.py`）は本フェーズでは触らない（02 の SSoT を尊重する）
   - `.claude/rules/backend.md` に「§ディレクトリ構成（`apps/api/app/`）」「§レイヤ間の import 方向」セクションが無い、または `§A` / `§C` / `§D` と矛盾する → 機械可読版に展開して追加 or 書き換える（手順 4 が SSoT）
   - `.claude/CLAUDE.md` の「ルールファイルの管理」リストに `backend.md` が無ければ追加する
6. **完了後に検証コマンドを必ず流す**：`mise run api:lint` / `mise run api:typecheck` / `mise run api:test` を順に実行し、3 つすべて clean になることを確認する。失敗があれば修正して再実行（ユーザーに投げ返さない）
7. **「書き換える」「削除する」「追加する」「リネームする」の解釈**：本ドキュメント中のこれらの動詞は、すべて**最終状態を §決定値 に合わせる作業**を指す。**初期状態がどうであれ、最終的に §決定値 と一致していればよい**：
   - 古い記述が存在する → 新しい記述に置き換える（書き換え）
   - 古い記述が存在しない（フレッシュ・スタート） → 新しい記述を追加するだけ（削除工程はスキップ）
   - 既に新しい記述になっている → 何もしない（idempotent）
   - 中途半端な状態（新旧混在 / typo / 別パス） → 不要な部分を消し、新しい記述に揃える

---

## 決定値（このフェーズで固定する、議論しない設計）

本フェーズの全ステップはこの決定値を元に作業する。**§自律実行ポリシー §1 により、この節の選択は議論しない**。

### A. ディレクトリ構成

```text
apps/api/app/
├── __init__.py                                      # 02-python.md 配置済
├── main.py                                          # FastAPI アプリ生成 + ルータ束ねる（02-python.md 配置済）
├── README.md                                        # 全体図 + やってはいけないこと（本フェーズで作成）
├── core/                                            # 設定 / セキュリティ / 例外ハンドラ等の横断ユーティリティ（終端）
│   ├── __init__.py                                  # 02-python.md 配置済
│   ├── README.md                                    # 本フェーズで作成
│   └── config.py                                    # pydantic-settings ベースの Settings + get_settings()（02-python.md 配置済）
├── db/                                              # SQLAlchemy エンジン / セッション / Base
│   ├── __init__.py                                  # 02-python.md 配置済
│   ├── README.md                                    # 本フェーズで作成
│   ├── base.py                                      # DeclarativeBase（02-python.md 配置済）
│   └── session.py                                   # AsyncEngine + AsyncSessionLocal + get_async_session（02-python.md 配置済）
├── models/                                          # SQLAlchemy モデル（1 テーブル 1 ファイル）
│   ├── __init__.py                                  # 全モデルを re-export（Alembic autogenerate が拾う）（02-python.md 配置済）
│   ├── README.md                                    # 本フェーズで作成
│   └── health_check.py                              # 疎通確認用最小テーブル（02-python.md 配置済）
├── schemas/                                         # Pydantic モデル（SSoT、HTTP API + Job キュー両境界に展開、ADR 0006）
│   ├── __init__.py                                  # 02-python.md 配置済
│   ├── README.md                                    # 本フェーズで作成
│   └── health.py                                    # HealthCheckResponse（02-python.md 配置済）
├── routers/                                         # APIRouter（機能別 controller 相当、薄い受付係）
│   ├── __init__.py                                  # 02-python.md 配置済
│   ├── README.md                                    # 本フェーズで作成
│   ├── health.py                                    # POST/GET /health（DB 往復、02-python.md 配置済）
│   └── probes.py                                    # GET /healthz（liveness、02-python.md 配置済）
├── services/                                        # ビジネスロジック + SQLAlchemy クエリ（R1 以降で実体化）
│   ├── __init__.py                                  # 本フェーズで作成（空ファイル）
│   └── README.md                                    # 本フェーズで作成
├── deps/                                            # 依存性注入（Depends で使う関数群、認証ガード等）（R1 以降で実体化）
│   ├── __init__.py                                  # 本フェーズで作成（空ファイル）
│   └── README.md                                    # 本フェーズで作成
└── observability/                                   # OpenTelemetry / 構造化ログ / メトリクス（R4 以降で実体化）
    ├── __init__.py                                  # 本フェーズで作成（空ファイル）
    └── README.md                                    # 本フェーズで作成
```

> **既存実装ファイル**（02-python.md 配置済、本フェーズでは触らない）：`main.py` / `core/config.py` / `db/base.py` / `db/session.py` / `models/health_check.py` / `models/__init__.py`（`from app.models.health_check import HealthCheck` を re-export）/ `schemas/health.py` / `routers/health.py` / `routers/probes.py`。中身の SSoT は [02-python.md](./02-python.md) の各 step。
>
> **`services/` `deps/` `observability/` が空フォルダで残る理由**：R0 段階では業務機能（auth / problems 等）が未着手のため、これらレイヤに置く実装ファイルがまだ無い。R1 以降の機能追加に合わせて埋まる。R0 では `__init__.py` + `README.md` だけを置いて空フォルダ防止と意図の明示を兼ねる。
>
> **`__init__.py` を全フォルダに置く理由**：Python の規約。空ファイルでもよいが、`app.models` のように `from app.<layer> import ...` で参照する箱として認識させるために必要。

### B. 配置に関する重要な選択（なぜそうしたか）

| 論点 | 採用 | 不採用 | 採用理由 |
|---|---|---|---|
| レイヤ分割の粒度 | **機能別フラット 8 レイヤ**（routers / services / schemas / models / core / db / deps / observability） | DDD 風 4 層（presentation / application / domain / infrastructure）| 個人〜小規模 SaaS 規模では DDD 4 層は過剰。FastAPI 公式 example の慣習に揃え、初学者が読みやすい一段構成に倒す（→ [ADR 0034](../../../adr/0034-fastapi-for-backend.md)）|
| Repository レイヤ | **不採用**（Service が `AsyncSession` から SQLAlchemy 2.0 を直接呼ぶ単層構成） | Service → Repository → ORM の 2 段構成 | 本 Backend は ADR 0040 により責務が薄い（auth + CRUD + job enqueue + 結果取得のみ）。Repository は ORM への delegating wrapper になりやすく ROI が低い。複雑なクエリが複数 Service で重複し始めたら `app/queries/<feature>.py` の関数群に切り出す段階導入で対応する（→ [02-architecture.md: 設計スタイル](../../2-foundation/02-architecture.md#設計スタイル) / [ADR 0038](../../../adr/0038-test-frameworks.md)）|
| admin / customer 分割 | **不採用**（全機能を 1 つの routers/ で扱う、認可は `Depends` で制御） | `routers/admin/` と `routers/customer/` でディレクトリ分け | 同じリソース（problems / submissions 等）を扱うエンドポイントが分散しロジックが重複するため。認可の有無は `dependencies=[Depends(require_admin)]` の差分で表現する |
| 横断的な部品の置き場 | **責務に近い場所**（例：`get_current_user` は `app/deps/auth.py`、`get_async_session` は `app/deps/db.py`、`Settings` は `app/core/config.py`）| 1 箇所の `app/common/` に集約 | 「いつ・どう使うか」が違う部品を同居させると、`Depends` 用の関数とただのクラス・定数が混ざって読みにくくなる |
| LLM 呼び出しの置き場 | **Worker 側に閉じる**（`apps/workers/grading/` / `apps/workers/generation/`） | Backend に `app/llm/` を作って共有 | 「ユーザー応答性」と「LLM 呼び出しの長さ」を分離するため。Backend は enqueue + 結果取得のみに留め、LLM SDK（`anthropic` / `google-genai` 等）を `apps/api/` に置かない（→ [ADR 0040](../../../adr/0040-worker-grouping-and-llm-in-worker.md)）|
| 各サブフォルダの README | **全 8 サブフォルダ + `app/` トップに 1 個ずつ**（合計 9 個）| README 無し（`.gitkeep` で空フォルダ防止のみ） | 初学者が階層を辿る時に「このフォルダ何？」で迷わない。空フォルダ防止の `.gitkeep` も README が兼ねる。`/` の段階で実体ファイルが無いレイヤ（services / deps / observability）も README が意図を残す |

### C. レイヤ間の import 方向

新規機能追加時、各レイヤから何を import してよいかを下記表で固定する。R1 以降の全機能実装はこの契約に従う。

| レイヤ | import してよい | import 禁止 |
|---|---|---|
| `routers/` | `services` / `schemas` / `deps` / `core` | `models` / `db` を直接（health_check のような trivial ケースは明示的例外） |
| `services/` | 他の `services` / `models` / `schemas` / `queries`（必要時）/ `db` / `core` | `routers` / `deps` / `main` |
| `queries/`（必要時、R1 以降に段階導入） | `models` / `db` / `core` | `services` / `routers` / `schemas` |
| `deps/` | `services` / `db` / `core` | `routers` / `main` |
| `schemas/` | `core` のみ | 上位レイヤ全て |
| `models/` | `db.base` / `core` | 上位レイヤ全て |
| `db/` | `core` | 上位レイヤ全て |
| `core/` | （何も import しない、終端） | 全て |
| `observability/` | `core`（設定値の参照のみ） | 業務レイヤ全て |

**補足ルール**：

- **依存は一方向**：A → B かつ B → A を作らない。`services/` 内の機能間も同じ（例：`grading` → `submissions` の向きに揃え、逆向き import を作らない）
- **副作用は直接 import で繋がない**：通知・発火等は FastAPI の `BackgroundTasks` または domain event 経由で起動し、別 router / service を直接 import しない
- **`schemas/` を終端に保つ**：TS / Go への型生成（[ADR 0006](../../../adr/0006-json-schema-as-single-source-of-truth.md)）の境界を壊さないため、`schemas/` から業務レイヤを import しない
- **`models/` の型注釈用途は例外**：`schemas/<feature>.py` の `from_attributes=True` は型情報を必要としないので `from app.models...` は不要だが、Service 内で SQLAlchemy モデルの型注釈として参照するのは OK
- **trivial 例外**：`health_check` のような INSERT 1 行 / SELECT 1 行レベルは Service を作らず router 直書きを許容（[02-python.md: 7. 薄い CRUD エンドポイント](./02-python.md#7-薄い-crud-エンドポイント--pytest-疎通) の設計判断に従う）

### D. 命名規則

| 種別 | 命名パターン | 例 |
|---|---|---|
| ファイル名・パッケージ名 | snake_case | `health_check.py` / `problems.py` / `core/` |
| クラス名（モデル / スキーマ / Service） | PascalCase | `HealthCheck` / `ProblemService` / `Settings` |
| 関数・変数 | snake_case | `get_async_session` / `current_user` / `query_client` |
| 定数 | SCREAMING_SNAKE_CASE | `JST_TIMEZONE` / `MAX_PAGE_SIZE` |
| SQLAlchemy テーブル名 | 複数形 snake_case | `health_check` / `problems` / `submissions` |
| Pydantic DTO の suffix | `<Model>Create` / `<Model>Update` / `<Model>Response` / `<Model>Query` | `ProblemCreate` / `ProblemUpdate` / `ProblemResponse` / `ProblemQuery` |
| ジョブペイロードスキーマ | `<JobName>Payload` | `GradingJobPayload` / `GenerationJobPayload` |
| 例外クラス | `<Domain>Error` | `ResourceNotFoundError` / `PermissionDeniedError` |
| Depends 用関数 | `get_*` / `require_*` | `get_current_user` / `get_async_session` / `require_admin` |

### E. 「やってはいけないこと」（NG パターン一覧）

`app/README.md` および `backend.md` の OK/NG コード片で取り上げる代表 NG。各 README は本リストから該当する項目を 2〜4 件抜粋して転記する。

#### E-1. 配置・import の NG

1. `routers/` から `models/` を直接 import して DB を触る（DB 操作は services を経由、`§C`。trivial な health_check のみ例外）
2. `routers/` から `db.session` を直接 import（`AsyncSession` の取得は `deps/db.py` 経由）
3. `services/` から `routers/` を import（逆流、`§C`）
4. `services/` から `deps/` を import（逆流。`current_user` は引数で受け取る、`§C`）
5. `schemas/` から `services/` や `models/` を import（schemas は終端、型生成境界を壊す、`§C`）
6. `core/` から業務レイヤ（services / routers / models 等）を import（core は終端、`§C`）
7. `app/llm/` のように LLM SDK を Backend 内に置く（LLM は Worker に閉じる、[ADR 0040](../../../adr/0040-worker-grouping-and-llm-in-worker.md)）
8. `app/routers/admin/` `app/routers/customer/` のようにユーザー種別でディレクトリ分割（`§B`、認可は `Depends` で表現）

#### E-2. 実装の NG

9. `services/` 内で `HTTPException(404, ...)` を直接投げる（ドメイン例外（`ResourceNotFoundError` 等）を投げ、`core/exceptions.py` の handler で HTTP に変換する）
10. Repository クラスを作って Service → Repository → ORM の 2 段構成にする（`§B`、Repository は不採用）
11. `Any` 型を使う（`Mapped[T]` / Pydantic モデル / `TypedDict` で型付け、[.claude/rules/backend.md](../../../../.claude/rules/backend.md) コーディング規約）
12. 認証済みエンドポイントで「自分のリソースか」のチェックを書き忘れる（例：`Submission.user_id == current_user.id` を付け忘れて他人の提出を返す）
13. `col.in_(ids)` の前に `len(ids) == 0` ガードを書かない（空リスト渡しで SQL エラー）
14. ソフトデリート用カラム（`deleted_at` 等）を追加する（ハードデリート方針、[.claude/rules/backend.md](../../../../.claude/rules/backend.md)）
15. `Depends()` を引数のデフォルト値に書く（`session: AsyncSession = Depends(get_async_session)` は ruff B008 違反、`Annotated[AsyncSession, Depends(get_async_session)]` を使う）

---

## 1. ディレクトリ構造の最終状態

**目的**：`apps/api/app/` 配下に Backend のレイヤを 1 つの方針で固定する。以降の機能実装はこの 8 フォルダのどこに置くかを判断するだけ、という状態を作る。

**最終状態**（§自律実行ポリシー §7 の通り、初期状態のばらつきは問わない）：

- `apps/api/app/` 配下が §A のツリーに一致している：
  - 8 レイヤすべて存在する：`routers/` / `services/` / `schemas/` / `models/` / `core/` / `db/` / `deps/` / `observability/`
  - 各レイヤに `__init__.py` がある（Python パッケージとして認識させるため、空でも OK）
  - `main.py` が存在し、`include_router(probes.router)` / `include_router(health.router)` で 02-python.md 配置済の 2 router を登録している
- **計 9 個の `README.md` ファイル**が存在する：
  - `apps/api/app/README.md`（1 個、`app/` 直下）
  - 上記 8 レイヤそれぞれに `README.md`（8 個）
  - 中身は手順 2 / 手順 3 で作る。本手順 1 の段階では空ファイルでもよい（最終的に手順 2 / 3 で書き込めば OK）
- `.gitkeep` ファイルが残っていない（README が空フォルダ防止を兼ねるため、`.gitkeep` は不要）
- §A のツリーに無い別のフォルダ（例：`app/llm/` のような LLM 用、`app/utils/` のような曖昧な名前のフォルダ、admin / customer の分割等）が残っていない

**02-python.md 完了済を前提とした、本フェーズで実際に新規追加する差分**：

> 前提フェーズ（[02-python.md](./02-python.md)）完了時点で、`routers/` / `schemas/` / `models/` / `core/` / `db/` の 5 ディレクトリと、それらに属する実装ファイル（`main.py` / `core/config.py` / `db/base.py` / `db/session.py` / `models/__init__.py` + `models/health_check.py` / `schemas/health.py` / `routers/health.py` / `routers/probes.py`）は既に配置済。**本フェーズはその上に「足りないレイヤ 3 つ」と「全レイヤの README + 実装契約」を載せるだけ**で、02-python.md 由来の既存ファイルには手を入れない。
>
> | 差分カテゴリ | 中身 |
> |---|---|
> | **新規フォルダ（3 個）** | `services/` / `deps/` / `observability/`（各 `__init__.py` を空ファイルで配置） |
> | **新規 README（9 個）** | `app/README.md` + 8 レイヤ分の `README.md`（02 配置済の 5 レイヤにも README が無いので追加する。本フェーズ手順 2 / 3 で書き込む） |
> | **実装契約の追加 / 整合化** | `.claude/rules/backend.md` に §A ツリー + §C import 方向表 + §D 命名規則 + OK/NG コード片を追加（または既存セクションを `§決定値` に合わせて整合化）。詳細は手順 4 |
> | **触らないもの** | 02-python.md 配置済の `main.py` / `core/config.py` / `db/base.py` / `db/session.py` / `models/health_check.py` / `models/__init__.py` / `schemas/health.py` / `routers/health.py` / `routers/probes.py`、および `alembic/` / `tests/` / `pyproject.toml` / `uv.lock` / `.env.example` |

**完了基準**：

- 上記 9 個の README.md が（空でも可）存在する
- 8 レイヤすべてが空ではない（`__init__.py` + README 入り）
- 02-python.md 配置済の実装ファイル（`main.py` / `core/config.py` / `db/base.py` / `db/session.py` / `models/health_check.py` / `schemas/health.py` / `routers/health.py` / `routers/probes.py`）に変更が入っていない
- `mise run api:lint` / `mise run api:typecheck` / `mise run api:test` が clean で通る（既存の health_check 結合テストも引き続き green）
- `mise run api:dev` でサーバが起動し、`curl http://localhost:8000/healthz` が `{"status":"ok"}` を返す（liveness 疎通）+ `/docs`（Swagger UI）で `health` / `probes` の 2 タグが表示される

**関連 ADR**：[ADR 0034](../../../adr/0034-fastapi-for-backend.md)（FastAPI 採用、機能別フラット構成）/ [ADR 0037](../../../adr/0037-sqlalchemy-alembic-for-database.md)（SQLAlchemy 2.0 + Alembic）/ [ADR 0006](../../../adr/0006-json-schema-as-single-source-of-truth.md)（Pydantic SSoT、`schemas/` を境界に置く理由）/ [ADR 0040](../../../adr/0040-worker-grouping-and-llm-in-worker.md)（LLM Worker 集約、Backend が薄い責務になる根拠）

---

## 2. 各レイヤの README.md の最終状態

**目的**：各サブフォルダに人間向けの 1 ファイル README を置き、初学者が階層を辿る時に「このフォルダは何の置き場か」を即把握できるようにする。Frontend レイヤ分割フェーズと同じ書き分け方針。

**最終状態**（全 README が下記の構成を満たす）：

各 README は以下のセクションを含む。すべてのフォルダで全セクション必須ではなく、必要なものを取捨選択する：

| セクション | 役目 | 必須か |
|---|---|---|
| `## <フォルダ名>/ とは何か` | そのレイヤが扱う仕組みと、比喩的な役割（受付係 / 実務担当 / 設計図 / 部品工場 / 計測装置 等）を 1〜2 行で書く。`§A` のツリーコメントがそのまま叩き台 | 必須 |
| `## 役目` or `## ファイル配置` | 1 機能 1 ファイルの慣習、命名規則（DTO の suffix 等）、依頼関係を 2〜5 行で書く | 任意（取捨選択） |
| `## 機能パターン一覧（🟢 使う / 🔴 使わなさそう）` | core / deps / observability のように「ここに置けるものが幅広い」レイヤでは、代表パターンを 🟢 / 🔴 に分けて列挙し、各パターンに「何のために」「無いとどう困るか」を 2〜4 行で書く | 任意（core / deps / observability では推奨） |
| `## 他レイヤとの違い` | 紛らわしい組（`core/` と `deps/`、`schemas/` と `models/`、`lib/api/`（Frontend）と `__generated__/api/` のような対）には観点別の対比表を入れる | 任意（混同しやすい組では必須） |
| `## やってはいけないこと` | `§E` の NG パターン一覧から該当する項目を **2〜4 件**抜粋（router 系 README は `§E-1` 中心、services 系 README は `§E-1` + `§E-2` の認可 / Repository、schemas 系 README は `§E-1` の境界違反、core 系 README は `§E-1` の終端違反等。各 README の文脈に該当する NG が少ない場合は 1〜2 件でもよい） | 必須 |

**書き方の規約**：

- **コード片は書かない**：人間向けに概念ベースで書く。コード片は Claude 用 rules ファイル（`backend.md`）に集約する。命名規則の具体例（`<Model>Response` 等）が説明に必要な場合は短い断片を含めてよい
- **専門用語の扱い**：[コメントスタイル](../../../../.claude/CLAUDE.md#コメントの書き方) に従い、SSoT / DI / hydration / Server Component 等の専門用語は使わず平易な日本語で書く。「依存性注入」も「リクエストごとに必要なものを差し込む仕組み」のように噛み砕く
- **他レイヤへのリンク**：相対パスで「中身は [services/](../services/)」「規約は [.claude/rules/backend.md](../../../../.claude/rules/backend.md)」のように指す

**最終状態で存在すべき README**（全 9 ファイル）：

| パス | 重視する内容 |
|---|---|
| `apps/api/app/README.md` | トップの全体図（手順 3 で詳述） |
| `apps/api/app/routers/README.md` | 「URL の受付係」の役目 / `Depends` で前処理を受け取る / 業務処理は services に丸投げ |
| `apps/api/app/services/README.md` | 「業務処理本体」の役目 / DB クエリ + 認可チェック / `routers` を import 禁止 / 結果は `schemas` に詰め替えて返す |
| `apps/api/app/schemas/README.md` | Pydantic が型の SSoT / `<Model>Create/Update/Response/Query` の命名 / TS / Go への型生成境界 |
| `apps/api/app/models/README.md` | SQLAlchemy モデル = DB テーブルの設計図 / Alembic autogenerate が拾う / schemas（JSON）とは別物 |
| `apps/api/app/core/README.md` | 横断ユーティリティ（設定 / 例外 / 鍵 / OAuth クライアント） / 終端で他を import しない / `deps/` との違い対比表 |
| `apps/api/app/db/README.md` | `AsyncEngine`（接続プール）+ `AsyncSession`（1 リクエスト 1 つ）+ `Base`（モデル共通親）/ 実 SQL は services 側 |
| `apps/api/app/deps/README.md` | `Depends` で router 引数に差し込む関数群 / `get_async_session` / `get_current_user` / `require_admin` / `core/` との違い対比表 |
| `apps/api/app/observability/README.md` | ログ / メトリクス / トレースの初期化（R4 以降）/ `main.py` 起動時 1 回だけ呼ぶ / 業務コードからは触らない |

### 2-1. `core/` `deps/` `observability/` の README に書く 🟢/🔴 パターンシード

これら 3 レイヤは「ここに置けるものが幅広い」性質を持つため、README に「**機能パターン一覧（🟢 使う / 🔴 使わなさそう）**」セクションを設けて、本プロジェクトで採用する / しないパターンを明示する。各パターンに「**何のために**」「**無いとどう困るか**」を 2〜4 行で書く（コード片は書かず、概念ベース）。

下記はフレッシュ Claude が README をゼロから書く時に**項目を取りこぼさないためのシード**。各項目の説明文は ADR / `.claude/rules/backend.md` を読んで肉付けする。

#### 2-1-a. `core/README.md` のパターンシード（🟢 7 件 / 🔴 9 件）

🟢 採用する（プロジェクトで使うパターン）：

| # | 項目 | 何のために（要点）| 根拠 |
|---|---|---|---|
| 1 | アプリ設定値の管理（`config.py`）| `.env` / 環境変数から読み込んだ設定値を型付きで一元管理（pydantic-settings ベースの `Settings` + `get_settings()`）| 02-python.md step 4 配置済 |
| 2 | ドメイン例外クラス（`exceptions.py`、予定）| 業務エラーを HTTP 文脈に依存せず表現。Service は `ResourceNotFoundError` 等を投げるだけ、core/ の handler が 404 等に変換 | — |
| 3 | Cookie 署名の道具と秘密鍵（`security.py`、予定）| session_id 改ざん検知のための `itsdangerous` 署名器と秘密鍵を 1 箇所に集める。署名は services 側が利用、検証は deps 側 | [ADR 0011](../../../adr/0011-github-oauth-with-extensible-design.md) |
| 4 | OAuth クライアントの設定（`oauth.py` or `security.py`、予定）| GitHub OAuth の client_id / secret / redirect_uri / scope を集中管理。将来 Google OAuth 追加時もファイル 1 つ増えるだけ | [ADR 0011](../../../adr/0011-github-oauth-with-extensible-design.md) |
| 5 | 共通レスポンス型（`schemas/common/` or `core/responses.py`、予定）| `Page[T]` / `PaginationMeta` / `ErrorResponse` のような全 API 共通の応答形を 1 度だけ定義 | — |
| 6 | 共通定数（`constants.py`、予定）| ジョブ状態名（"queued" / "running" / "completed"）等のマジック文字列を排除 | — |
| 7 | タイムゾーン定義（`timezones.py` or `config.py` 内、予定）| 「DB は UTC、表示は JST」を 1 箇所で固定（`JST = ZoneInfo("Asia/Tokyo")`）| — |

🔴 不採用（このプロジェクトでは出番が無いパターン）：

| # | 項目 | 不採用理由 |
|---|---|---|
| 1 | DI コンテナ（`dependency-injector` / `punq` 等）| FastAPI の `Depends` で完結 |
| 2 | メッセージブローカー抽象（`MessageBus` / `EventBus`）| ジョブキューは Postgres LISTEN/NOTIFY で完結（[ADR 0004](../../../adr/0004-postgres-as-job-queue.md)）|
| 3 | KMS / 鍵管理サービス抽象 | `.env` + SSM Parameter Store / Secrets Manager で十分 |
| 4 | メール送信抽象（`MailService`）| MVP に通知機能無し（R6 以降で再評価） |
| 5 | キャッシュ抽象レイヤ（`Cache` インタフェース）| Redis 固定（[ADR 0005](../../../adr/0005-redis-not-for-job-queue.md)）、`redis-py` 直接で足りる |
| 6 | マルチテナント設定（`TenantContext`）| 個人ユーザー単位の単一テナント |
| 7 | ロケール / i18n 基盤 | 日本語のみで運用 |
| 8 | 機能フラグ（`FeatureFlags` / LaunchDarkly 抽象）| 個人開発で A/B テスト無し |
| 9 | 監査ログ機構（`AuditLogger`）| 個人学習用途で監査要件無し、Loki への通常ログで十分 |

#### 2-1-b. `deps/README.md` のパターンシード（🟢 6 件 / 🔴 7 件）

🟢 採用する：

| # | 項目 | 何のために（要点）| 根拠 |
|---|---|---|---|
| 1 | DB セッションの貸し出し（`get_async_session`）| リクエスト開始時に開き、終了時に確実に閉じる処理を 1 箇所に集約。閉じ忘れによる接続プール枯渇を構造的に防ぐ | 02-python.md step 4 で配置済 / R1 で `deps/db.py` に移植 |
| 2 | ログイン中ユーザーの取得（`get_current_user`）| 未ログインを 401 で弾き、ログイン済みなら User オブジェクトを差し込む。認証必須 router は「current_user を受け取る」と書くだけで済む | [ADR 0011](../../../adr/0011-github-oauth-with-extensible-design.md) |
| 3 | 認可ガード（`require_admin` 等）| 権限不足を 403 で宣言的に弾く。`dependencies=[Depends(require_admin)]` で書き忘れ防止 | — |
| 4 | ページネーション引数の正規化（`pagination_params`）| `?page=X&limit=Y` の解釈ルール（マイナス値ガード・上限）を全 list API で揃える | — |
| 5 | レート制限チェック（`slowapi` 統合）| Bot 連打や LLM API コスト暴走を防ぐ。Redis 側でカウンタ共有 | [01-non-functional.md](../../2-foundation/01-non-functional.md) |
| 6 | リクエスト ID の採番（`get_correlation_id`）| observability の trace_id 自動付与の起点。`X-Request-Id` を尊重 + なければ自動採番 | observability/ と連動 |

🔴 不採用：

| # | 項目 | 不採用理由 |
|---|---|---|
| 1 | Bearer Token / API キー認証 | Web UI 経由の Cookie 認証のみ、サーバー間 API 無し |
| 2 | CSRF Token 検証 | `SameSite=Lax` Cookie + 同一オリジン Fetch で済む |
| 3 | ファイルアップロードの一時保存 | コード入力テキストのみ、添付機能無し |
| 4 | 多言語化（Accept-Language）| 日本語のみ運用 |
| 5 | テナント識別（マルチテナント）| 単一テナント |
| 6 | WebSocket セッション管理 | ジョブ進捗確認は HTTP polling 採用、WebSocket 不使用 |
| 7 | API レイヤのレスポンスキャッシュ取得 | 同じリクエストが連続する場面が少なく投資対効果低。LLM 出力キャッシュは Worker 側 |

#### 2-1-c. `observability/README.md` のパターンシード（🟢 8 件 / 🔴 9 件）

🟢 採用する：

| # | 項目 | 何のために（要点）| 採用プロダクト / 根拠 |
|---|---|---|---|
| 1 | 構造化ログ（JSON ログ）| Loki 側で「`user_id = X` かつ `level = ERROR`」のような絞り込みを可能にする | Loki（[ADR 0041](../../../adr/0041-observability-stack-grafana-and-sentry.md)）|
| 2 | trace_id / correlation_id の自動付与 | 1 ユーザー操作が API → DB → Worker → LLM と渡る流れを 1 ID で横断追跡 | Tempo / Loki / Sentry 全てに同一 ID 注入 |
| 3 | リクエスト / レスポンスのロギング | デプロイ後の 5xx 増加・レイテンシ悪化を能動検知 | Loki + Grafana ダッシュボード |
| 4 | Prometheus メトリクス出力 | 全体傾向（リクエスト数・平均レイテンシ・DB コネクション数）を時系列で蓄積、閾値超えで自動アラート | Prometheus + Grafana |
| 5 | OpenTelemetry トレース（分散トレース）| 「DB クエリ 3 秒 / LLM 8 秒 / JSON 変換 0.1 秒」のような関数レベルの内訳を本番リクエスト 1 本で確認 | Tempo |
| 6 | Sentry への例外送信 | ハンドル外の例外発生を即通知 + スタックトレース・リクエスト情報を 1 画面で確認、類似エラー自動グルーピング | Sentry |
| 7 | ジョブキュー深さのメトリクス | LLM 呼び出し詰まりの早期検知。`jobs` テーブル未処理件数を Prometheus に流す | Prometheus（本プロジェクトで最重要指標の 1 つ） |
| 8 | ヘルスチェック（`/healthz` / `/readyz`）| k8s / ALB がインスタンスの受付可否を機械可読に判定、デプロイ時の無停止切替を支える | 02-python.md step 8 で `/healthz` 配置済、`/readyz` は R1 以降 |

🔴 不採用：

| # | 項目 | 不採用理由 |
|---|---|---|
| 1 | Datadog / New Relic / Honeycomb 等の商用 APM | Grafana スタック自前運用でコストを抑える（[ADR 0041](../../../adr/0041-observability-stack-grafana-and-sentry.md)）|
| 2 | PagerDuty / Opsgenie 連携 | 個人ポートフォリオで SLA 無し、Sentry のメール / Slack 通知で十分 |
| 3 | ユーザー行動分析（Mixpanel / Amplitude）| ポートフォリオ用途で行動分析より先に動くもの優先 |
| 4 | プロファイラ（Pyroscope / py-spy）| Prometheus のレイテンシヒストグラムで十分、関数単位プロファイラまで不要 |
| 5 | eBPF ベースの可視化（Pixie / Cilium Hubble）| 単一 EC2 / コンテナ規模でネットワーク詳細不要 |
| 6 | セッションリプレイ（Sentry Replay / LogRocket）| Backend 主体で UI バグ調査優先度低 |
| 7 | RUM（Real User Monitoring）の Backend 統合 | Frontend 側 Sentry Browser SDK で完結 |
| 8 | CloudWatch / Stackdriver | Grafana に集約（ベンダーロックイン回避） |
| 9 | ELK / Splunk | Loki と機能が被り、Loki の方が軽量で本プロジェクト規模に合う |

> **書き方の指針**：各 README は上記の項目名 + 「何のために」を素直に転記しつつ、初学者向けに「無いとどう困るか」を 2〜4 行で肉付けする。専門用語は使わず平易な日本語で（[コメントスタイル](../../../../.claude/CLAUDE.md#コメントの書き方)）。コード片は書かない（Claude 用 rules ファイル側の役割）。

---

**完了基準**：

- 上記 9 個の README.md が存在する
- 各 README は「とは何か」セクションを冒頭に持つ
- 紛らわしいレイヤ組（`core/` と `deps/`、`schemas/` と `models/`、`routers/health.py` と `routers/probes.py`）には対比的な記述がある
- `core/` `deps/` `observability/` の 3 つには `§2-1` のシードに沿った 🟢/🔴 機能パターン一覧が含まれている（採用 / 不採用の項目数が一致 or 同等）
- 全 README で `§E` の NG パターンから該当する 1〜4 件が「やってはいけないこと」または本文の戒めとして転記されている

---

## 3. `app/README.md` の最終状態

**目的**：人間が `apps/api/app/` 直下を開いた時に、レイヤ間の呼び出しの向きが 1 枚の図で見て取れる状態にする。

**最終状態**（`apps/api/app/README.md` が下記をすべて含む）：

A. **レイヤ一覧表**：8 レイヤ + `main.py` を「これは何か（役目）」付きで表にし、各セルから対応する README へリンクが張られている

B. **ASCII 図でレイヤ間の呼び出し方向**を示す。`§C` の import 方向と一致する：

   叩き台（実際の図は `app/README.md` 内に書く）：
   ```text
                     [リクエスト]
                          │
                          ▼
                     ┌─────────┐                ┌─────────┐
                     │ routers │───────────────►│ schemas │  response_model
                     └────┬────┘                └─────────┘
                 ┌────────┴────────┐
          Depends で取り出す   直接呼び出す
                 │                  │
                 ▼                  ▼
             ┌──────┐         ┌──────────┐      ┌─────────┐
             │ deps │────────►│ services │─────►│ schemas │  model_validate
             └──┬───┘         └────┬─────┘      └─────────┘  (models → schemas へ詰め替え)
                │                  │
                │              ┌───┴────┐
                │              ▼        ▼
                │           ┌────┐  ┌────────┐
                └──────────►│ db │◄─┤ models │
                            └────┘  └────────┘
   ```

   - `schemas` は参照タイミングが 2 つあるため意図的に 2 度描く（右上 = routers がレスポンス形を宣言、右下 = services が SQLAlchemy モデルを Pydantic に詰め替え）
   - `core` / `observability` は別系統として図外に補足

C. **読み方の具体例**が含まれる：
   - 正常な流れ（`/problems` → `routers/problems.py` → `services/problems.py` → `models/problems.py` → DB → `schemas/problems.py` 経由で返す）
   - `deps/` が間に入る場合（ユーザー取得 = `Depends(get_current_user)` / DB セッション = `Depends(get_async_session)`）
   - `core/` が終端である意味（設定・例外を全レイヤから呼べるが、core から業務レイヤを呼び返さない）
   - `observability/` が別系統である意味（起動時に `main.py` から 1 回だけ初期化、業務コードからは触らない）

D. **`## やってはいけないこと` セクション**が `§E` の NG パターン一覧から **4 件以上**を箇条書きで含む（`§E-1` 配置・import 系を中心に、`§E-2` の実装 NG も適宜含める）

**完了基準**：

- `apps/api/app/README.md` を開けば「何の機能がどう繋がるか」が図 + 補足で完結する
- 「やってはいけないこと」が `§E` から 4 件以上列挙されている
- 図中の矢印が `§C` の import 方向表と一致している

---

## 4. 実装契約を `.claude/rules/backend.md` に固定

**目的**：Claude が新規実装時に参照する「実装契約」として、ディレクトリ配置 + import 方向 + 命名規則 + Router / Service / Pydantic スキーマの書き方を、表 + コード片で曖昧さなく固定する。人間向け README が「概念で理解する」のに対し、rules ファイルは「パターンマッチで判定する」用途。

### 4-1. `.claude/rules/backend.md` の最終状態

`§自律実行ポリシー §7` の通り、初期状態（既存セクションの有無 / 旧パス記載の有無 / 内容のズレ）は不問。**最終状態が下記の条件をすべて満たしていればよい**。既存セクションが条件と矛盾する場合は整合させ、無ければ追加し、すでに一致していれば何もしない。

A. **`## ディレクトリ構成（`apps/api/app/`）` セクションが存在する**（または同等の包括セクションが 1 つ存在する）。内容は次を含む：
- `§A` のツリー（コメント付き）
- 「Repository レイヤは採用しない」「admin / customer 分割は採用しない」「横断的な部品は責務に近い場所」「LLM SDK は Backend に置かない」の 4 つの設計方針
- `§C` への内部リンク（または `§C` の表を直接ここに転記）

B. **`### レイヤ間の import 方向` セクションが存在する**。内容は次を含む：
- `§C` の import 可 / 禁止表（8〜9 レイヤすべてが行として並ぶ）
- `§C` の補足ルール（依存一方向 / 副作用は `BackgroundTasks` / `schemas/` を終端 / trivial 例外）
- OK / NG コード片を **4 例以上** `.python` コードブロックで含む：
  - ✅ `routers` が `services` / `schemas` / `deps` を import して `Depends` で session を受け取る
  - ❌ `routers` が `models` / `db.session` を直接 import（trivial 例外を除く）
  - ❌ `services` が `routers` / `deps` を import（逆流）
  - ❌ `schemas` が `services` / `models` を import（終端違反）

C. **`### 設計方針` セクション**が「admin / customer 分割不採用」「`Depends` で認証要否切替」「横断部品は責務に近い場所」「Repository 不採用 + 段階的 `queries/` 切り出し」の 4 点を含む

D. **`## API ルートと認証` セクション**が以下を含む：
- REST リソース単位のパス設計（例：`/problems` / `/submissions` / `/auth/github`）
- Swagger UI / Redoc / OpenAPI 3.1 JSON の URL（[ADR 0006](../../../adr/0006-json-schema-as-single-source-of-truth.md)）
- 認証：Authlib + GitHub OAuth + Cookie + Redis（[ADR 0011](../../../adr/0011-github-oauth-with-extensible-design.md)）
- 全ルートデフォルト認証必須 + 個別 router で `dependencies=[]` 上書き（public 用）

E. **`## データベース（Postgres + SQLAlchemy 2.0 async）` セクション**が以下を含む：
- AsyncEngine + AsyncSession、Service レイヤは `async def`
- セッション取得：`Annotated[AsyncSession, Depends(get_async_session)]`（B008 違反回避）
- タイムゾーン：`TIMESTAMP(timezone=True)` で UTC、表示は JST
- IDs：UUID（`gen_random_uuid()`）または BigInteger（`jobs.id` のみ）
- ハードデリート方針（ソフトデリート不採用）
- where 条件の必須ルール（`user_id == current_user.id` / `len(ids) == 0` ガード）

F. **`## ジョブキュー（Postgres `jobs` テーブル）` セクション**が以下を含む：
- `INSERT INTO jobs` + `NOTIFY new_job, <jobId>` を同一トランザクション（[ADR 0004](../../../adr/0004-postgres-as-job-queue.md)）
- ペイロード Pydantic は `app/schemas/jobs/<job_type>.py`
- `model.model_json_schema()` で `apps/api/job-schemas/` に書き出し → quicktype で Go struct 生成（[ADR 0006](../../../adr/0006-json-schema-as-single-source-of-truth.md)）

G. **`## LLM 呼び出し` セクション**が「LLM 呼び出しは Worker 側に閉じ、Backend は呼ばない」を明示し、[ADR 0040](../../../adr/0040-worker-grouping-and-llm-in-worker.md) を引用している

H. **`## コーディング規約` セクション**が以下を含む：
- ruff（lint + format）/ pyright / 設定の SSoT が `apps/api/pyproject.toml`
- **`Any` 利用不可**、`Mapped[T]` / Pydantic / `TypedDict` で型付け
- `import` は ruff の `isort` ルールで自動整列、手動整列禁止
- モジュール名は snake_case、クラス名は PascalCase、テーブル名は複数形

I. **`### Router` / `### Pydantic スキーマ（SSoT）` / `### Service` の 3 サブセクション**が `§D` の命名規則表 + 書き方ルール（`prefix` + `tags`、`response_model` 必須、`<Model>Create/Update/Response/Query` 命名、`async with session.begin()` のトランザクション境界等）を含む

J. **`## 新規機能の追加パターン` セクション**が「`/backend-new-module` スキル使用 or 手動で 4 ステップ（models / schemas / services / routers）+ `include_router` + Alembic マイグレーション」を含む

K. **`## テスト` セクション**が以下を含む：
- ユニット（`tests/unit/`）/ 結合（`tests/integration/`）/ E2E（`tests/e2e/`）の 3 階層
- Repository モック不採用の理由（false positive を生むため）
- テスト関数名・docstring は日本語

L. **`## ツーリング` セクション**が `mise run api:*` タスク表を含む（パッケージ管理 / lint+format / 型 / 脆弱性 / 依存衛生 / テスト）

> **書き換え方の指針**：上記の「**最終的にこうなっていればよい**」を満たすために、既存ファイルから関連箇所を探して整合させる。一致しているものは触らない、無いものは足す、矛盾しているものは書き換える（§自律実行ポリシー §7）。

### 4-2. `.claude/CLAUDE.md` の最終状態

- `.claude/CLAUDE.md` の「ルールファイルの管理」リストに `.claude/rules/backend.md` が列挙されている：「バックエンド（FastAPI / Python）に関すること → `.claude/rules/backend.md`」の 1 行が存在する
- 該当行が無ければ追加し、別パスを指している場合は修正する

### 4-3. 共通の最終状態

- `backend.md` が [claude-rules-authoring.md](../../../../.claude/rules/claude-rules-authoring.md) の書き方規約に従っている（リンクではなく直接記載、表 / 箇条書きで列挙、本拠地がある場合は冒頭でリードを付ける）
- `backend.md` の SQLAlchemy / Alembic スキーマ・マイグレーションの詳細は [.claude/rules/alembic-sqlalchemy.md](../../../../.claude/rules/alembic-sqlalchemy.md) に委譲し、本ファイルは概要 + リンクのみで済ます（重複回避、SSoT 原則）

**完了基準**：

- `backend.md` の「§ディレクトリ構成（`apps/api/app/`）」セクションに `§A` のツリー + 設計方針 4 点 + `§C` の import 方向表 + OK/NG 例（4 例以上）が揃っている
- import 方向表に 8〜9 レイヤすべてが行として並ぶ
- OK/NG コード片で「DB 操作目的 NG」と「型注釈用途 OK」が区別できる
- `## API ルートと認証` / `## データベース` / `## ジョブキュー` / `## LLM 呼び出し` / `## コーディング規約` / `## 新規機能の追加パターン` / `## テスト` / `## ツーリング` の各セクションが揃っている
- `CLAUDE.md` の「ルールファイルの管理」リストに `backend.md` が列挙されている

---

## 5. 進捗トラッカーへの反映の最終状態

**目的**：本フェーズが終わったことを、プロジェクトの進捗管理仕組み（ロードマップ / プロジェクト管理ツール / README 等）に反映する。

**最終状態**：

- **プロジェクトの進捗トラッカー**（このプロジェクトでは [docs/requirements/5-roadmap/01-roadmap.md](../01-roadmap.md)。別プロジェクトでは GitHub Project / Notion / README 等、各プロジェクトの慣習に従う）で、本フェーズに該当する項目が**完了状態**として記録されている
- 進捗トラッカー上の該当エントリから、**本ファイル**（または同等の手順詳細）への**リンク**が辿れる
- 本ファイル冒頭のステータスマーク（`# 05. Backend レイヤ分割（✅ 完了）` の `✅`）が完了状態を示している

> **このプロジェクトでの具体例**：[01-roadmap.md](../01-roadmap.md) の R0-5 行が、状態列 `✅ 完了` + 詳細手順列が本ファイルへのリンク `[r0-setup/05-backend-layers.md](./r0-setup/05-backend-layers.md)` になっている状態。古い表現（`🔴 未着手` / 未着手プレースホルダ / 旧リンク等）が残っていれば最終状態に合わせる。

**完了基準**：

- 進捗トラッカー上で本フェーズが完了になっている
- 本ファイルへのリンクが進捗トラッカーから辿れる
- 本ファイル冒頭のステータスマークが完了状態（`✅`）になっている

---

## 関連

- 親階層：[README.md: 言語別 setup の後段](./README.md#言語別-setup-の後段レイヤ分割フェーズ)
- 前フェーズ：[02-python.md](./02-python.md)（apps/api workspace + Postgres + Alembic + 最小 health_check の配置元）
- 次フェーズ：[06-frontend-layers.md](./06-frontend-layers.md)
- ロードマップ：[01-roadmap.md: Now：R0 基盤](../01-roadmap.md#nowr0-基盤直列初期慣行--言語別環境構築--レイヤ分割)
- 実装契約 SSoT：[.claude/rules/backend.md](../../../../.claude/rules/backend.md)
- SQLAlchemy / Alembic 詳細規約：[.claude/rules/alembic-sqlalchemy.md](../../../../.claude/rules/alembic-sqlalchemy.md)
- 人間向けレイヤ概要：[apps/api/app/README.md](../../../../apps/api/app/README.md)
- 関連 ADR：[ADR 0034](../../../adr/0034-fastapi-for-backend.md)（FastAPI 採用、機能別フラット構成）/ [ADR 0037](../../../adr/0037-sqlalchemy-alembic-for-database.md)（SQLAlchemy 2.0 + Alembic）/ [ADR 0006](../../../adr/0006-json-schema-as-single-source-of-truth.md)（Pydantic SSoT、`schemas/` を境界に置く根拠）/ [ADR 0040](../../../adr/0040-worker-grouping-and-llm-in-worker.md)（LLM Worker 集約、Backend が薄い責務になる根拠）/ [ADR 0011](../../../adr/0011-github-oauth-with-extensible-design.md)（GitHub OAuth）/ [ADR 0004](../../../adr/0004-postgres-as-job-queue.md)（Postgres ジョブキュー）/ [ADR 0038](../../../adr/0038-test-frameworks.md)（テストフレームワーク、Repository モック不採用の根拠）
