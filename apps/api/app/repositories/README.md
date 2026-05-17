# repositories/

## repositories/ とは何か

1 機能の「**DB アクセスの窓口**」を集める置き場。
1 機能 1 ファイル（例：`problems.py` / `submissions.py`）に Repository クラス（`ProblemRepository` / `SubmissionRepository`）として書く。

repositories の関数は **「DB との会話だけを担当する窓口」** の役割で、ここに書くのは：

- SQLAlchemy のクエリ組み立てと実行（`select` / `insert` / `update` / `delete` + `await session.execute(...)`）
- 複雑な JOIN や eager loading（`selectinload` / `joinedload`）
- DB から取り出した結果を **そのまま（ORM オブジェクトのまま）返す**

ここに書かないもの（[services/](../services/) の責務）：

- ビジネスロジック（計算・分岐・条件判断）
- 認可チェック（「自分のリソースか？」）— ただし `user_id == current_user.id` を WHERE 条件として受け取って実行するのは OK
- トランザクション境界（`async with session.begin():` は Service 側で握る）
- Pydantic への詰め替え（ORM → [schemas/](../schemas/) は Service の仕事）

## 役目

- [services/](../services/) から呼ばれて、DB アクセスを実行する
- 戻り値は ORM オブジェクト（`<Feature>` のインスタンス、または `list[<Feature>]`、または `None`）
- `AsyncSession` は `__init__` で受け取る（Service が DI で渡してくる）

## なぜこのレイヤを置くか（ポートフォリオ駆動）

Backend の責務は薄い（auth + CRUD + ジョブ enqueue + 結果取得のみ、→ [ADR 0040](../../../../docs/adr/0040-worker-grouping-and-llm-in-worker.md)）ため、
ROI 観点だけ見れば Service が SQLAlchemy を直接呼ぶ「単層構成」のほうが効率的。

それでも本プロジェクトは Repository レイヤを置く判断をしている。理由：

- **ポートフォリオで設計パターンの理解を可視化する**：採用面接で `apps/api/app/repositories/` の存在自体が「Service / Repository / ORM の 3 層分離を理解している」シグナルになる
- **テストの分離**：Service の単体テストは Repository を `AsyncMock` でスタブ化、Repository は実 DB に対して SQL 挙動を結合テスト、という責務分離の 2 段構成が組める
- **読み手の認知負荷低減**：ビジネスロジックと DB クエリが物理的に別ファイルになり、grep で責務境界が即特定できる

詳細な判断根拠とトレードオフは [ADR 0044](../../../../docs/adr/0044-backend-repository-pattern-adoption.md) を参照。

## services/ との違い

| 観点 | services/ | repositories/ |
|---|---|---|
| 担当範囲 | ビジネスロジック・認可・分岐・Pydantic 詰め替え・トランザクション境界 | SQLAlchemy クエリの実装のみ |
| 戻り値 | Pydantic レスポンス（`<Feature>Response`） | ORM オブジェクト（`<Feature>`） |
| `async with session.begin():` | ここで握る | 書かない（Service の境界に乗る） |
| `HTTPException` / ドメイン例外 | 投げる（404 / 403 / バリデーション失敗） | 投げない（None を返すか、例外は Service に判断を委ねる） |
| import 可 | `repositories` / 他の `services` / `schemas` / `models`（型注釈）/ `core` | `models` / `db` / `core` のみ |

## ファイル配置

- 1 集約 1 ファイル：`app/repositories/<feature>.py`
- クラス名は `<Feature>Repository`（PascalCase）。例：`ProblemRepository` / `SubmissionRepository`
- 名前は機能の単数形（テーブル名は複数形でも、クラスは単数形）

## やってはいけないこと

- ❌ `schemas/` を import（戻り値は ORM、Pydantic 変換は Service の責務）
- ❌ `services/` を import（逆流）
- ❌ `routers/` / `deps/` を import（さらなる逆流）
- ❌ `async with session.begin():` を Repository 内に書く（トランザクション境界は Service が握る）
- ❌ ビジネスロジック（計算・分岐）を Repository 内に書く（Service に持っていく）

ルールの正本（表形式・コード例付き）は [.claude/rules/backend.md](../../../../.claude/rules/backend.md)。
