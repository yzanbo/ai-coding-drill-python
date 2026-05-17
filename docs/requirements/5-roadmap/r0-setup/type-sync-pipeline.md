# 型同期パイプライン基盤構築（🔴 未着手）

## このフェーズで何ができるようになるか

1. **Python で 1 箇所書けば、TS が勝手に追従する**：Backend の Pydantic（[apps/api/app/schemas/](../../../../apps/api/app/schemas/)）を書き換えるだけで、Frontend の TS 型 + Zod + 型付き HTTP クライアントが自動再生成される。手で TS の型を書き直す作業がゼロになる
2. **API 仕様書が副産物としてタダで手に入る**：Pydantic を書くと FastAPI が `/docs`（Swagger UI）と `/openapi.json` を自動配信。仕様書を別途書く必要がない
3. **型を更新し忘れた PR が構造的にマージできない**：pre-commit hook（ローカル早期検出）+ CI `types-gen-drift` ジョブ（最終ゲート）の二重防御で、「Backend だけ直して Frontend の型が古いまま」のバグが原理的に発生しない
4. **Worker（Go）側合流の土台が揃う**：ジョブ payload 用 JSON Schema を吐く仕組み（`apps/api/job-schemas/`）を本フェーズで稼働させ、後続フェーズで Go の quicktype がそのまま読み込める状態にする
5. **ジョブ payload Pydantic を追加するだけの運用に乗る**：機能実装フェーズで `apps/api/app/schemas/jobs/<name>.py` に `<Name>JobPayload` クラスを 1 個書くだけで、自動収集により JSON Schema artifact が増える（手作業で export 対象を増やす必要なし）

**本フェーズではまだできないこと**：Worker（Go）側で型を消費すること（後続の Worker 側合流フェーズで対応）/ 実際のジョブ payload 型定義（R1 以降の機能実装と一緒に追加）。

---

> **守備範囲**：Pydantic SSoT（[apps/api/app/schemas/](../../../../apps/api/app/schemas/)）から **HTTP API 境界 artifact**（`apps/api/openapi.json`）と **Job キュー境界 artifact**（`apps/api/job-schemas/<name>.schema.json`）を機械的に書き出し、Frontend 側で **Hey API**（`@hey-api/openapi-ts` + Zod プラグイン）が OpenAPI を消費して TS 型 + Zod + 型付き HTTP クライアントを生成するまでの end-to-end 経路を確立する。さらに drift（Pydantic 変更後 artifact 未更新）を **lefthook**（早期検出）と **CI**（最終ゲート）の二軸で構造的に防ぐ。本フェーズが終わると、Backend で Pydantic を 1 箇所書き換えるだけで Frontend が型・Zod・HTTP クライアントを自動追従できる状態になる。
> **前提フェーズ**：[Backend レイヤ分割フェーズ](./backend-layers.md) 完了済（`apps/api/app/schemas/` が確定し `schemas/__init__.py` が機能している、`apps/api/app/main.py` から `/openapi.json` が取得できる、`apps/web/src/__generated__/api/` ディレクトリが配置済）
> **次フェーズ**：Worker（Go）側合流フェーズ（quicktype で `apps/api/job-schemas/` から Go struct を生成、`worker:types-gen` の CI 組込みまで。本フェーズの artifact をそのまま入力源として再利用するため、本フェーズが先行完了している必要がある）
>
> **本ファイル共通の最新版調査ポリシー**：
> [.claude/CLAUDE.md: バージョン方針](../../../../.claude/CLAUDE.md#バージョン方針) に従い、各ステップで **(1) 対象ツールの最新安定版を毎回 Web で調査** し、**(2) 採用前に依存関係（peer dep / 必須最小版数 / breaking changes）をリリースノートで確認** してから書き換える。SSoT（`apps/api/pyproject.toml` + `apps/api/uv.lock` / `apps/web/package.json` + `apps/web/pnpm-lock.yaml`）に書かれた既存版数には追従しない（陳腐化のため）。RC / beta / nightly は採用しない。本フェーズの対象は **`@hey-api/openapi-ts` + Zod プラグイン**（Frontend 側生成器）。Pydantic / FastAPI 本体の版数は Backend 環境構築フェーズで pin 済のため触らない。
>
> **本フェーズ共通の設計原則**：「環境構築 + 品質ゲート 5 ステップ」パターンと hook 役割分担（pre-commit / pre-push / CI）は [README.md](./README.md) を参照。本フェーズは Backend + Frontend を跨ぐが、新規ランタイムを入れない（既存 uv / pnpm にツール 1 つ追加する）ため `mise install` ステップは無く、生成スクリプト追加 → 品質ゲート組込みの順で進む。
>
> **本フェーズと [ADR 0006](../../../adr/0006-json-schema-as-single-source-of-truth.md) の役割分担**：本ファイルが「**手順 + 設定値**」の SSoT、ADR 0006 が「**SSoT 戦略 + 境界別 2 伝送路の採用根拠**」の SSoT。drift 検出の運用ルール詳細は [2-foundation/06-dev-workflow.md: drift 検出（lefthook + CI 二軸）](../../2-foundation/06-dev-workflow.md#drift-検出lefthook--ci-二軸) を参照。本ファイルは「上記方針を本フェーズでどう実装に落とすか」だけを扱う。

---

## 自律実行ポリシー（Claude が本ファイルを読んで作業する時の前提）

本ファイルは Claude に**そのまま実行を依頼**する想定で書かれている。次の原則を守って、ユーザーに確認を取らずに最後まで進める。

1. **ユーザーに設計上の確認を求めない**：Pydantic SSoT + 境界別 2 伝送路（OpenAPI 3.1 / 個別 JSON Schema）/ Frontend 生成器に Hey API を採用 / `apps/web/src/__generated__/api/` 配下を生成物コミット対象 / drift 検出を lefthook + CI 二軸で守る — これらは [ADR 0006](../../../adr/0006-json-schema-as-single-source-of-truth.md) で決定済みのため再検討しない。
2. **本フェーズでは Go 側は触らない**：quicktype 導入 / `apps/workers/grading/internal/jobtypes/` 生成 / `worker:*:types-gen` の CI 組込みは後続の Worker 側合流フェーズで実施する。本フェーズは Frontend までの 2 言語（Python + TS）で end-to-end 疎通させる範囲にとどめる。ただし **Pydantic → JSON Schema export スクリプト本体（`scripts/export_job_schemas.py`）と `mise run api:job-schemas-export` タスクは本フェーズで稼働させる**（Go 側合流フェーズが artifact 入力源として参照するため）。
3. **新規ブランチを切ってから作業する**：[CLAUDE.md: ブランチ運用](../../../../.claude/CLAUDE.md#ブランチ運用) に従い、`feature/shared/type-sync-pipeline`（または同等の `feature/shared/<名前>`）で作業する。本フェーズは Backend + Frontend を跨ぎ共有 artifact（`apps/api/openapi.json` / `apps/api/job-schemas/`）を生む性質のため scope は `shared` を使う（→ [CLAUDE.md: コミットメッセージ](../../../../.claude/CLAUDE.md#コミットメッセージ) の scope 表）。
4. **コミット・PR 作成は明示指示があるまで行わない**：[CLAUDE.md: Git 操作の禁止](../../../../.claude/CLAUDE.md#git-操作の禁止) に従い、`git add` / `git commit` / `git push` / PR 作成はユーザーから明示指示が出るまで保留する。ファイル作成・編集は自動で進めてよい。

---

## このフェーズで下す決定（§決定値）

本フェーズで確定させる値（手順本体より先に提示し、各ステップでこの値を参照する）：

| 項目 | 値 | 根拠 |
|---|---|---|
| HTTP API 境界 artifact のパス | `apps/api/openapi.json`（コミット対象） | [ADR 0006: 配置物理パス](../../../adr/0006-json-schema-as-single-source-of-truth.md#配置物理パス) |
| Job キュー境界 artifact のパス | `apps/api/job-schemas/<job-name>.schema.json`（コミット対象、本フェーズ時点ではディレクトリのみ作成、Pydantic ジョブモデルが追加されたら順次ファイルが増える） | 同上 |
| OpenAPI export スクリプト | `apps/api/scripts/export_openapi.py`（`uv run python -m scripts.export_openapi`） | mise.toml `[tasks."api:openapi-export"]` の `run` |
| JSON Schema export スクリプト | `apps/api/scripts/export_job_schemas.py`（`uv run python -m scripts.export_job_schemas`） | mise.toml `[tasks."api:job-schemas-export"]` の `run` |
| ジョブ payload Pydantic の配置規約 | `apps/api/app/schemas/jobs/<job_type>.py` 配下に 1 ジョブ 1 モデル（クラス名末尾 `JobPayload`、export スクリプトはこの命名規約で自動収集する） | [.claude/rules/backend.md: ジョブキュー](../../../../.claude/rules/backend.md#ジョブキューpostgres-jobs-テーブル) |
| Frontend 生成器 | `@hey-api/openapi-ts` + Zod プラグイン（pnpm の `apps/web` に devDep 追加） | [ADR 0006: 言語別の生成ツール](../../../adr/0006-json-schema-as-single-source-of-truth.md#言語別の生成ツール) |
| Frontend 生成物のパス | `apps/web/src/__generated__/api/`（コミット対象、Biome / tsc / Knip の対象外設定） | 同上 |
| Hey API 設定ファイル | `apps/web/openapi-ts.config.ts`（TS で書く、型補完が効くため。→ [CLAUDE.md: 設定ファイル形式の優先順位](../../../../.claude/CLAUDE.md#設定ファイル形式の優先順位)） | — |
| drift 検出の責務分担 | lefthook で早期 feedback（Pydantic 変更時のみ起動）、CI で最終ゲート（`git diff --exit-code` で fail-closed） | [06-dev-workflow.md: drift 検出（lefthook + CI 二軸）](../../2-foundation/06-dev-workflow.md#drift-検出lefthook--ci-二軸) |

---

## 1. OpenAPI 3.1 export スクリプト配置（apps/api 側）

**目的**：FastAPI が起動時にメモリ上で組み立てる OpenAPI 3.1 ドキュメントを、ファイルシステム上の artifact（`apps/api/openapi.json`）として固定し、Frontend / CI の drift 検出から参照できるようにする。FastAPI を実際に HTTP serve せずに `app.openapi()` を直接呼ぶことで、依存（DB / Redis / GitHub OAuth 等）の起動なしに artifact 化できる。

**設計判断**：
- **FastAPI を `uvicorn` で起動せず `app.openapi()` を直接呼ぶ**：DB 接続や設定値（`GITHUB_CLIENT_ID` 等）の有無に左右されず、CI でも空の `.env` で完走させたい。`app/main.py` の `app` インスタンスを import するだけで OpenAPI 3.1 dict が手に入る（FastAPI の標準 API）
- **出力は整形 JSON（`indent=2` + 末尾改行）**：git diff の可読性を最優先。生成物コミット運用（→ [ADR 0006](../../../adr/0006-json-schema-as-single-source-of-truth.md)）では diff レビューが効くフォーマットが必須
- **キーソート（`sort_keys=True`）**：Pydantic の出力順は微妙な変更で揺れることがあるため、機械的に固定して「中身は同じだが順序だけ違う」差分を抑制する

**作業内容**：
1. `apps/api/scripts/` ディレクトリを新規作成し、空の `__init__.py` を配置（`-m scripts.export_openapi` 実行のため Python パッケージ化）
2. `apps/api/scripts/export_openapi.py` を作成：
   - `from app.main import app` で FastAPI インスタンスを import
   - `app.openapi()` の戻り値（dict）を `json.dumps(spec, indent=2, sort_keys=True, ensure_ascii=False)` で文字列化
   - `apps/api/openapi.json` に書き出し（末尾改行を 1 つ付ける）
   - 既存 artifact と内容が同一なら write を skip して mtime を保つ（git diff ノイズを増やさないため）
3. ファイル冒頭に **役割 / 出力先 / 設計判断** の 3 ブロックをコメントで記述する（同ディレクトリの `export_job_schemas.py` と相互参照させ、両者が「Pydantic SSoT → 境界別 artifact」の 2 本柱であることを片方を読めば分かる状態にする）

**完了確認**：
```bash
cd apps/api && mise exec -- uv run python -m scripts.export_openapi
# → 標準出力に「wrote apps/api/openapi.json (XXX bytes)」等のメッセージ
ls -la apps/api/openapi.json                              # ファイルが生成されている
jq '.openapi' apps/api/openapi.json                       # "3.1.0"
jq '.paths | keys' apps/api/openapi.json                  # ["/health", "/healthz"] 等が出る
jq '.components.schemas | keys' apps/api/openapi.json     # ["HealthCheckResponse", ...] が出る
```

**前提**：[Backend レイヤ分割フェーズ](./backend-layers.md) 完了（`apps/api/app/schemas/` 配下が確定）

**関連 ADR**：[ADR 0006](../../../adr/0006-json-schema-as-single-source-of-truth.md) / [ADR 0034](../../../adr/0034-fastapi-for-backend.md)

---

## 2. Pydantic → JSON Schema export スクリプト配置（apps/api 側）

**目的**：Job キュー境界の payload を表す Pydantic モデル群を自動収集し、各モデルから `model.model_json_schema()` で個別 JSON Schema ファイル（`apps/api/job-schemas/<job-name>.schema.json`）を書き出す。Worker 側合流フェーズの quicktype に渡す入力源を確定させる。

**設計判断**：
- **ジョブ payload の配置規約は `apps/api/app/schemas/jobs/<job_type>.py` 1 ファイル 1 ジョブ**：export スクリプトは `app.schemas.jobs` パッケージ配下を再帰 import し、`BaseModel` の subclass のうちクラス名が `JobPayload` で終わるものを対象とする（誤検出を避けるための suffix 規約）
- **出力ファイル名は class 名 → kebab-case 変換**：`GradingJobPayload` → `grading.schema.json`（`JobPayload` suffix を取り除き、CamelCase → kebab-case 変換）。Worker 側 quicktype の `--src` に渡しやすい単純な命名
- **本フェーズ時点ではモデル 0 個でも script は完走させる**：`apps/api/job-schemas/` ディレクトリは作成し `.gitkeep` を置く。スクリプトは「対象モデル 0 個、wrote 0 schemas」を標準出力に流して exit 0。これにより mise タスクと CI ステップは本フェーズで配線完了でき、後続の機能実装フェーズで Pydantic モデルが追加されると自動でファイルが増える設計
- **JSON フォーマットは OpenAPI export と同条件**（`indent=2` + `sort_keys=True` + `ensure_ascii=False` + 末尾改行 + 内容同一なら skip）：git diff 可読性と drift 検出の安定性を揃える

**作業内容**：
1. `apps/api/app/schemas/jobs/` ディレクトリを新規作成し、空の `__init__.py` を配置（後続フェーズでジョブ payload Pydantic を追加する空き地）
2. `apps/api/job-schemas/` ディレクトリを新規作成し、`.gitkeep` を配置（artifact 出力先、本フェーズ時点では空）
3. `apps/api/scripts/export_job_schemas.py` を作成：
   - `pkgutil.walk_packages` で `app.schemas.jobs` 配下のモジュールを再帰 import
   - 各モジュール内で `BaseModel` の subclass を列挙し、クラス名が `JobPayload` で終わるものを対象に追加
   - 各クラスについて `cls.model_json_schema()` で JSON Schema dict を取得 → kebab-case ファイル名で `apps/api/job-schemas/<name>.schema.json` に書き出し
   - 対象 0 個でもエラーにせず「wrote 0 schemas（対象クラスなし）」を標準出力に流して exit 0
4. ファイル冒頭に **役割 / 出力先 / 命名規約 / 設計判断** の 4 ブロックをコメントで記述する（`export_openapi.py` と相互参照させる）
5. **ジョブ payload Pydantic は本フェーズでは追加しない**（[01-roadmap.md](../01-roadmap.md) の本フェーズに該当する行の脚注に従い、機能実装フェーズで一緒に追加する）

**完了確認**：
```bash
cd apps/api && mise exec -- uv run python -m scripts.export_job_schemas
# → 「wrote 0 schemas（対象クラスなし、apps/api/app/schemas/jobs/ に *JobPayload を追加すると自動収集される）」
ls apps/api/job-schemas/                       # .gitkeep のみ
```

**前提**：本ファイルの「1. OpenAPI 3.1 export スクリプト配置」（`scripts/` パッケージが既存）

**関連 ADR**：[ADR 0006](../../../adr/0006-json-schema-as-single-source-of-truth.md) / [ADR 0004](../../../adr/0004-postgres-as-job-queue.md)

---

## 3. mise の `api:openapi-export` / `api:job-schemas-export` タスク稼働確認

**目的**：[mise.toml](../../../../mise.toml) に**先回りで定義済み**の `api:openapi-export` / `api:job-schemas-export` タスクが、本フェーズで配置したスクリプトと整合して動作することを確認する。**追記はしない**（mise.toml はタスク定義済、スクリプト実体側を本フェーズで揃える順序）。

**前提済の登録タスク**（[mise.toml](../../../../mise.toml) の `[tasks."api:openapi-export"]` / `[tasks."api:job-schemas-export"]`、本ステップでは追記不要）：

- `api:openapi-export` — `uv run python -m scripts.export_openapi`
- `api:job-schemas-export` — `uv run python -m scripts.export_job_schemas`

**作業内容**：
1. `mise tasks | grep ^api:` で両タスクが list されることを確認
2. 両タスクを順に起動：
   - `mise run api:openapi-export` → `apps/api/openapi.json` が更新（または skip）、exit 0
   - `mise run api:job-schemas-export` → `apps/api/job-schemas/` が更新（本フェーズ時点では `.gitkeep` のみで実 schema 0 件）、exit 0
3. 2 回連続で実行して `git status` に差分が出ないことを確認（冪等性）

**完了確認**：上記 2 タスクが緑で抜け、2 回目以降は差分が出ない。

**関連 ADR**：[ADR 0039](../../../adr/0039-mise-for-task-runner-and-tool-versions.md)

---

## 4. Hey API 導入と Frontend 生成器設定（apps/web 側）

**目的**：Frontend 側で `apps/api/openapi.json` を消費し、TS 型 + Zod スキーマ + 型付き HTTP クライアントを `apps/web/src/__generated__/api/` に生成する経路を確立する。

**設計判断**：
- **Hey API 採用根拠**は [ADR 0006: TS（Frontend）の生成ツール](../../../adr/0006-json-schema-as-single-source-of-truth.md#ts-frontend-の生成ツール) を参照（本フェーズでは決定済として扱い、再検討しない）
- **設定ファイルは TS（`apps/web/openapi-ts.config.ts`）**：Hey API は `UserConfig` 型を export しており、typo を保存時に IDE / `tsc` が即時に弾けるため。[CLAUDE.md: 設定ファイル形式の優先順位](../../../../.claude/CLAUDE.md#設定ファイル形式の優先順位) の優先順位 1（型 export あり → TS）
- **生成先 `apps/web/src/__generated__/api/` は既存ディレクトリ**：Frontend レイヤ分割フェーズで配置済（README あり）。本フェーズの生成物はそこに上書き出力する
- **Biome / tsc / Knip の対象外設定**：生成物は人間が手書きしないため、Biome の lint・Knip の未使用検出は除外する（`apps/web/biome.jsonc` `apps/web/knip.config.ts` を必要分だけ調整）。一方 `tsc --noEmit` は型整合性確認のため対象に含める（生成物が壊れていれば型エラーで検出されるべき）

**作業内容**：
1. **Hey API の最新安定版を調査**：[Hey API openapi-ts](https://heyapi.dev/openapi-ts/) と [Hey API Zod Plugin](https://heyapi.dev/openapi-ts/plugins/zod) で latest stable 版を確認
2. `cd apps/web && pnpm add -D @hey-api/openapi-ts` で devDep に追加（Zod プラグインが別 package の場合は同時追加、最新ドキュメントの指示に従う）
3. `apps/web/openapi-ts.config.ts` を作成：
   - `input`：相対パスで `../api/openapi.json`（apps/api の artifact を直接参照）
   - `output`：`./src/__generated__/api`
   - プラグイン：標準クライアント生成 + Zod スキーマ + TS 型（最新ドキュメントの推奨構成に従う、本ファイルでは API 名を凍結しない）
4. `apps/web/biome.jsonc` を編集：`files.includes` / `linter.includes` 等から `src/__generated__/**` を除外（生成物に lint をかけない）
5. `apps/web/knip.config.ts` を編集：`ignore` に `src/__generated__/**` を追加（未使用検出から除外、初期段階では生成物を import するアプリ側コードが無いため warn が出る）
6. **package.json の依存版数の意図**を `apps/web/package.json` の devDep コメント運用に従い記録（package.json はコメント不可のため、依存追加 commit メッセージ本文で根拠を残す）

**完了確認**：
```bash
mise run api:openapi-export                       # 入力 artifact を最新化
mise run web:types-gen                            # Hey API が走り、apps/web/src/__generated__/api/ 配下に TS / Zod / client が生成される
ls apps/web/src/__generated__/api/                # 生成ファイル群（具体名は Hey API バージョン依存）
mise run web:typecheck                            # 生成物が型エラーなく通る
mise run web:lint                                 # 生成物が lint 対象から除外されている
mise run web:knip                                 # 生成物が未使用検出から除外されている
```

**前提**：本ファイルの「3. mise の `api:openapi-export` / `api:job-schemas-export` タスク稼働確認」（入力源 `apps/api/openapi.json` が存在）

**関連 ADR**：[ADR 0006](../../../adr/0006-json-schema-as-single-source-of-truth.md)

---

## 5. mise の `web:types-gen` / 横断 `types-gen` タスク稼働確認

**目的**：[mise.toml](../../../../mise.toml) に**先回りで定義済み**の `web:types-gen` と横断 `types-gen` タスクが、本フェーズで配置した Hey API 設定と整合して動作することを確認する。

**前提済の登録タスク**（[mise.toml](../../../../mise.toml)、本ステップでは追記不要）：

- `web:types-gen` — `pnpm exec openapi-ts`（apps/web 配下、設定は `openapi-ts.config.ts`）
- `types-gen`（横断） — `depends` で `api:openapi-export` / `api:job-schemas-export` / `web:types-gen` / `worker:grading:types-gen` を順次実行

**作業内容**：
1. `mise tasks | grep types-gen` で `web:types-gen` / `types-gen` / `api:openapi-export` / `api:job-schemas-export` が list されることを確認
2. **動作するもの**：
   - `mise run web:types-gen` → Hey API が走り、`apps/web/src/__generated__/api/` 配下が更新（または skip）
3. **動作しないもの**（本フェーズの範囲外、後続の Worker 側合流フェーズで実装）：
   - `mise run types-gen` の `depends` に含まれる `worker:grading:types-gen` は quicktype 未導入のため fail する。本フェーズでは個別タスク（`api:openapi-export` / `api:job-schemas-export` / `web:types-gen`）の稼働で end-to-end 疎通を確認し、横断 `types-gen` の完走は後続フェーズの完了条件とする
4. 個別タスクを順に手動実行して 2 言語間の疎通を確認：
   ```bash
   mise run api:openapi-export && mise run api:job-schemas-export && mise run web:types-gen
   # → 3 タスク全て exit 0、生成物 3 箇所が更新される
   ```

**完了確認**：上記 3 タスクが直列で緑、2 回目以降は差分が出ない（冪等性）。

**関連 ADR**：[ADR 0039](../../../adr/0039-mise-for-task-runner-and-tool-versions.md) / [ADR 0006](../../../adr/0006-json-schema-as-single-source-of-truth.md)

---

## 6. lefthook.yml に Pydantic SSoT drift 検出 pre-commit 追加

**目的**：「Pydantic schema を変更したのに `apps/api/openapi.json` / `apps/api/job-schemas/` / `apps/web/src/__generated__/api/` の再エクスポートを忘れた commit」をローカル早期に弾く。

**設計判断**：
- **glob で SSoT 変更時のみ起動**：`apps/api/app/schemas/**/*.py` がステージング差分に含まれる時だけフックを走らせる。無関係な commit にコストを乗せない（→ [06-dev-workflow.md: drift 検出（lefthook + CI 二軸）](../../2-foundation/06-dev-workflow.md#drift-検出lefthook--ci-二軸)）
- **3 artifact をまとめて再生成し `git diff --exit-code` で abort**：再生成後に差分が出る = 開発者が再生成し忘れていた、または再生成を忘れた commit を抑止できる。差分が無ければ commit を通す
- **`mise exec --` 経由**：[Backend 環境構築フェーズ](./backend.md) の pre-commit と同じ理由（Git フックの非対話シェルに対する shims 解決）
- **本フェーズでは Worker 側生成物（quicktype）の drift は対象外**：Go 側合流フェーズで `apps/workers/<name>/internal/jobtypes/` は gitignore（→ [ADR 0006: 言語別の生成ツール](../../../adr/0006-json-schema-as-single-source-of-truth.md#言語別の生成ツール)）のため drift 検出対象に含めない（CI 内で都度生成して使う運用に揃える）

**追記内容**（[lefthook.yml](../../../../lefthook.yml) の `pre-commit` セクション）：

```yaml
pre-commit:
  parallel: true
  commands:
    # … 既存の api-ruff / api-pyright / web-biome / web-typecheck / web-knip はそのまま …

    # Pydantic SSoT → artifact 同期検証（ADR 0006）
    # apps/api/app/schemas/ 配下が変わったときだけ起動。3 artifact を再生成して差分が
    # 出たら abort し、開発者に「mise run api:openapi-export && mise run api:job-schemas-export
    # && mise run web:types-gen して再 commit」を促す。
    schemas-drift:
      glob: "apps/api/app/schemas/**/*.py"
      run: |
        mise exec -- mise run api:openapi-export
        mise exec -- mise run api:job-schemas-export
        mise exec -- mise run web:types-gen
        git diff --exit-code apps/api/openapi.json apps/api/job-schemas/ apps/web/src/__generated__/api/
      fail_text: |
        Pydantic schema 変更後の artifact 再生成が漏れています。下記を実行して再 commit してください：
          mise run api:openapi-export
          mise run api:job-schemas-export
          mise run web:types-gen
          git add apps/api/openapi.json apps/api/job-schemas/ apps/web/src/__generated__/api/
```

**完了確認**：
```bash
# 偽の Pydantic 変更を仕込んで drift を作る
echo "# touch" >> apps/api/app/schemas/health.py
git add apps/api/app/schemas/health.py
mise exec -- lefthook run pre-commit               # schemas-drift が起動（再生成して差分が無ければ pass）

# 実際に schema を壊して artifact 未更新の状態を作る
sed -i '' 's/HealthCheckResponse/HealthCheckResponse2/' apps/api/app/schemas/health.py
git add apps/api/app/schemas/health.py
mise exec -- lefthook run pre-commit               # schemas-drift が fail_text を出して exit 1
git restore --staged apps/api/app/schemas/health.py && git checkout apps/api/app/schemas/health.py
```

**前提**：本ファイルの「5. mise の `web:types-gen` / 横断 `types-gen` タスク稼働確認」

**関連 ADR**：[ADR 0006](../../../adr/0006-json-schema-as-single-source-of-truth.md)

---

## 7. GitHub Actions に型同期 drift 検出ジョブ追加

**目的**：[Backend 環境構築フェーズ](./backend.md#12-github-actions-に-python-ジョブ追加) で整備したワークフローに drift 検出ジョブを追加し、hook bypass された commit もリモートで弾く。

**設計判断（pre-commit hook と CI の二重防御）**：pre-commit hook は `--no-verify` でバイパスされ得るため、CI が **最後の砦**として `git diff --exit-code` で fail-closed させる。hook と CI の二重防御で「Pydantic 変更後の artifact 同期」を hook bypass 時にもリモートで保証する。

**追記内容**（[.github/workflows/ci.yml](../../../../.github/workflows/ci.yml)）：
- 新規ジョブ 1 種：`types-gen-drift`
  - `actions/checkout` → `jdx/mise-action`（SHA pin、内部で `mise install` 実行）
  - `mise run api:openapi-export && mise run api:job-schemas-export && mise run web:types-gen`
  - `git diff --exit-code apps/api/openapi.json apps/api/job-schemas/ apps/web/src/__generated__/api/`（差分があれば exit 1）
- `ci-success` の `needs:` に `types-gen-drift` を追加

**Worker 側生成物を CI 対象に含めない理由**：本フェーズの範囲外（後続の Worker 側合流フェーズで `worker:types-gen` を CI 必須ステップに追加する）。本フェーズでは `apps/api/openapi.json` / `apps/api/job-schemas/` / `apps/web/src/__generated__/api/` の 3 artifact のみを drift 検出対象とする。

**完了確認**：
- PR を作ると `types-gen-drift` ジョブが走る
- Pydantic 変更後に artifact 未更新の PR は `types-gen-drift` が赤、`ci-success` も赤になり、Branch protection で merge がブロックされる
- artifact を更新した PR は `types-gen-drift` が緑

**前提**：本ファイルの「6. lefthook.yml に Pydantic SSoT drift 検出 pre-commit 追加」（CI ジョブは `mise run` 群を呼ぶため、ローカルでタスクが動くことが必須）

**関連 ADR**：[ADR 0026](../../../adr/0026-github-actions-incremental-scope.md) / [ADR 0031](../../../adr/0031-ci-success-umbrella-job.md) / [ADR 0006](../../../adr/0006-json-schema-as-single-source-of-truth.md)

---

## 8. end-to-end 疎通の最終確認（`HealthCheckResponse` で 2 言語往復）

**目的**：本フェーズの成果物が「Backend で Pydantic を 1 箇所変更すると Frontend の TS 型 + Zod まで自動追従する」状態であることを、既存の `HealthCheckResponse` だけを使って閉路で検証する。本格的なジョブ payload Pydantic は機能実装フェーズで追加されるが、本フェーズ完了時点で疎通自体は確認できる粒度に揃える（[01-roadmap.md](../01-roadmap.md) の本フェーズに該当する行の脚注参照）。

**作業内容**：
1. `apps/api/openapi.json` を grep して `HealthCheckResponse` の定義が含まれることを確認
2. `apps/web/src/__generated__/api/` を grep して `HealthCheckResponse` 由来の TS 型 / Zod スキーマが生成されていることを確認
3. **疎通動作確認（任意、Frontend 実装契約を壊さない範囲で）**：`apps/web/src/lib/` 配下の任意のサンプルファイル（既存があれば流用、無ければ作らない）から、生成された型付き HTTP クライアントを import してコンパイルが通ることだけ確認する。実際の `GET /health` 呼び出し UI は本フェーズの責務外（機能実装フェーズで扱う）
4. `apps/api/app/schemas/health.py` の `HealthCheckResponse` に試しに 1 フィールド追加 → `mise run api:openapi-export && mise run web:types-gen` → Frontend 側の生成 TS 型に追加フィールドが反映されることを目視確認 → **必ず元に戻す**（本フェーズで Pydantic SSoT を実変更しない）

**完了確認**：
```bash
mise run api:openapi-export
mise run api:job-schemas-export
mise run web:types-gen
jq '.components.schemas.HealthCheckResponse' apps/api/openapi.json     # スキーマ定義が出る
grep -r "HealthCheckResponse" apps/web/src/__generated__/api/           # 生成物にヒット
mise run web:typecheck                                                  # 緑
mise run api:typecheck                                                  # 緑
git status                                                              # artifact / 生成物に差分なし（冪等）
```

**前提**：本ファイルの「7. GitHub Actions に型同期 drift 検出ジョブ追加」

---

## 9. 進捗トラッカーへの反映の最終状態

**目的**：本フェーズが終わったことを、プロジェクトの進捗管理仕組みに反映する。

**最終状態**：

- [01-roadmap.md](../01-roadmap.md) の本フェーズに該当する行が **完了状態**（`✅ 完了`）として記録されている
- 進捗トラッカー上の該当エントリから、**本ファイル**へのリンクが辿れる
- 本ファイル冒頭のステータスマーク（`# 型同期パイプライン基盤構築（🔴 未着手）` の `🔴 未着手`）が完了状態（`✅ 完了`）に書き換わっている
- リスクレジスタの「Pydantic SSoT → OpenAPI / JSON Schema → TS / Go 型生成の同期が崩れる」行の対応状況が、本フェーズで HTTP API 境界 + JSON Schema artifact の CI 必須化まで完了したことを反映している（Worker 側 `worker:types-gen` の CI 組込みは後続フェーズで実施、その旨が同行に書かれていれば追記不要）

**完了基準**：

- 進捗トラッカー上で本フェーズが完了になっている
- 本ファイルへのリンクが進捗トラッカーから辿れる
- 本ファイル冒頭のステータスマークが完了状態（`✅`）になっている

---

## このフェーズ完了時点で揃うもの

- 🟢 `mise run api:openapi-export` で `apps/api/openapi.json`（OpenAPI 3.1）が更新される
- 🟢 `mise run api:job-schemas-export` で `apps/api/job-schemas/` 配下に Pydantic ジョブ payload の個別 JSON Schema が出力される（本フェーズ時点では対象クラス 0 個、機能実装フェーズで自動増殖）
- 🟢 `mise run web:types-gen` で `apps/web/src/__generated__/api/` 配下に TS 型 + Zod + 型付き HTTP クライアントが生成される
- 🟢 Pydantic SSoT を変更したのに artifact 再生成を忘れた commit が **pre-commit hook で abort** される
- 🟢 hook bypass された PR も **CI の `types-gen-drift` ジョブで block** される
- 🟢 `HealthCheckResponse` のみで Backend → Frontend の 2 言語 end-to-end 疎通が確認できる

次は Worker 側合流フェーズで、本フェーズの artifact（`apps/api/job-schemas/`）を入力源として quicktype で Go struct 生成 + `worker:types-gen` の CI 組込みを行う。
