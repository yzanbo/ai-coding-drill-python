# 05. Backend レイヤ分割（✅ 完了）

> **守備範囲**：`apps/api/app/` 配下に機能別フラットなレイヤ分割（routers / services / schemas / models / core / db / deps / observability）を確定し、各レイヤの責務 + import 方向 + 命名規則を `.claude/rules/backend.md` に「実装契約」として固定する 4 ステップ。本フェーズが終わると、R1 以降の Backend 機能実装が「悩まずに迷わずレイヤを選ぶ」状態になる。
> **前提フェーズ**：[Python 環境構築フェーズ](./02-python.md)完了済（`apps/api/app/main.py` / `db/session.py` / `models/` の基本構造が存在し、`mise run api:dev` で起動可能）
> **次フェーズ**：Frontend レイヤ分割フェーズ（同ディレクトリ配下に新規作成予定）
>
> **本フェーズの位置付け**：[README.md: 言語別 setup の後段](./README.md#言語別-setup-の後段レイヤ分割フェーズ) を参照。言語ツーリングが整った上に、その言語側でプロジェクト固有のレイヤ分割を確定するフェーズで、「悩む余地のない基本構造」とは別物として扱う。
>
> **書き方の方針**：本フェーズは依存ライブラリのインストールを伴わないため、言語別フェーズの「環境構築 + 品質ゲート 5 ステップ」パターンには載らない。代わりに「**ディレクトリ確定 → 各レイヤ README → 全体図 → rules ファイルに実装契約として固定**」の 4 ステップで構成する。

---

## 1. レイヤ別ディレクトリの確定と空フォルダ作成

**目的**：`apps/api/app/` 配下に Backend のレイヤを 1 つの方針で固定する。以降の機能実装はこの 8 フォルダのいずれかにファイルを置くだけ、という状態を作る。

**作業内容**：
1. **8 レイヤを決める**：routers / services / schemas / models / core / db / deps / observability
2. **未作成のフォルダを作成**：以前の Python 環境構築フェーズで作られた routers / schemas / models / core / db に加え、本フェーズで services / deps / observability を新規作成
3. **各フォルダに `__init__.py` を配置**：空ファイルで OK（Python パッケージとして認識される）

**完了基準**：
- 8 つの `app/<layer>/__init__.py` がすべて存在する
- 既存の health_check テスト（`mise run api:test`）が引き続き通る

**関連 ADR**：[ADR 0034](../../../adr/0034-fastapi-for-backend.md)（FastAPI 採用、機能別フラット構成）/ [ADR 0040](../../../adr/0040-worker-grouping-and-llm-in-worker.md)（LLM Worker 集約により Backend は薄い責務）

---

## 2. 各レイヤの「とは何か」README.md を配置

**目的**：各サブフォルダに人間向けの 1 ファイル README を置き、初学者が階層を辿る時に「このフォルダは何の置き場か」を即把握できるようにする。

**作業内容**：
1. **「とは何か」セクション**：そのレイヤが扱う仕組みと、比喩的な役割（受付係 / 実務担当 / 設計図 等）を 1〜2 行で書く
2. **「機能パターン一覧」**：そのレイヤで扱える代表パターンを 🟢 このプロジェクトで使う / 🔴 使わなさそう に分けて列挙し、各パターンに「何のために」「無いとどう困るか」を 2〜4 行で書く
3. **「他レイヤとの違い」**：紛らわしいレイヤ（例：`core/` と `deps/`、`schemas/` と `models/`）には観点別の対比表を入れる
4. **コードは書かない**：人間向けに概念ベースで書く。コード片は Claude 用 rules ファイルに集約する（読み手の役割分担、→ [.claude/rules/claude-rules-authoring.md](../../../../.claude/rules/claude-rules-authoring.md)）

**完了基準**：
- 8 サブフォルダすべてに `README.md` がある
- 各 README は「とは何か」セクションを冒頭に持つ
- 紛らわしいレイヤ組には対比表がある

---

## 3. レイヤ全体図と「やってはいけないこと」を `app/README.md` に集約

**目的**：人間が `app/` 直下を開いた時に、レイヤ間の呼び出しの向きが 1 枚の図で見て取れる状態にする。

**作業内容**：
1. **レイヤ一覧表**：8 レイヤ + `main.py` を「これは何か（役目）」付きで表にする（各セルから対応する README へリンク）
2. **ASCII 図**：レイヤ間の呼び出し方向を矢印で表現（routers → deps → services → models → db 等）。`schemas` は参照タイミングが 2 箇所あるため意図的に 2 度描いてもよい
3. **読み方の具体例**：正常な流れ / deps が間に入る場合（ユーザー取得・DB セッション）/ core が終端である意味 / observability が別系統である意味
4. **やってはいけないこと**：❌ routers → models 直接 / ❌ services → routers / 等のよくある間違いを箇条書きで列挙

**完了基準**：
- `app/README.md` を開けば「何の機能がどう繋がるか」が図 + 補足で完結する
- 「やってはいけないこと」が 4〜6 件以上列挙されている

---

## 4. import 可 / 禁止と OK/NG コード片を rules ファイルに固定

**目的**：Claude が新規実装時に参照する「実装契約」として、import 方向のルールを表 + コード片で曖昧さなく固定する。人間向け README が「概念で理解する」のに対し、rules ファイルは「パターンマッチで判定する」用途。

**作業内容**：
1. **import 可 / 禁止表**：各レイヤから import してよいレイヤと禁止のレイヤを 2 列で列挙
2. **補足ルール**：一方向性 / 副作用は `BackgroundTasks` 経由 / `schemas` は終端 / 型注釈用途の `models` import は例外 等
3. **OK / NG コード片**：「routers が models を直接クエリ実行」「services が routers を import」「schemas が業務レイヤを import」のような NG パターンと、対応する OK パターンをコードで示す
4. **配置先**：Claude が自動 load する `.claude/rules/backend.md` 内に追記する。同フォルダ内の [claude-rules-authoring.md](../../../../.claude/rules/claude-rules-authoring.md) の書き方規約に従う

**完了基準**：
- `.claude/rules/backend.md` の「レイヤ間の import 方向」セクションに表と OK/NG 例がある
- 表に 8〜9 レイヤすべてが行として並ぶ
- OK/NG コード片で「DB 操作目的 NG」と「型注釈用途 OK」が区別できる

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
- ロードマップ：[01-roadmap.md: Now：R0 基盤](../01-roadmap.md#nowr0-基盤直列初期慣行--言語別環境構築--レイヤ分割)
- 実装契約 SSoT：[.claude/rules/backend.md](../../../../.claude/rules/backend.md)
- 人間向けレイヤ概要：[apps/api/app/README.md](../../../../apps/api/app/README.md)
- 関連 ADR：[ADR 0034](../../../adr/0034-fastapi-for-backend.md)（FastAPI 採用）/ [ADR 0040](../../../adr/0040-worker-grouping-and-llm-in-worker.md)（LLM Worker 集約）/ [ADR 0006](../../../adr/0006-json-schema-as-single-source-of-truth.md)（Pydantic SSoT）
