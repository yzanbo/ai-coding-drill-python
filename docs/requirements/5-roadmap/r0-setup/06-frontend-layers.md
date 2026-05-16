# 06. Frontend レイヤ分割（✅ 完了）

> **守備範囲**：`apps/web/src/` 配下に Next.js App Router 流のレイヤ分割（5 系統 14 フォルダ）を確定し、各レイヤの責務 + import 方向 + 命名規則を `.claude/rules/frontend.md` に「実装契約」として固定する。本フェーズが終わると、R1 以降の Frontend 機能実装が「悩まずに迷わずレイヤを選ぶ」状態になる。
> **前提フェーズ**：[Next.js 環境構築フェーズ](./03-frontend.md)完了済（`apps/web/src/app/{layout,page}.tsx` の基本構造が存在し、`mise run web:dev` で起動可能、Biome / Knip / syncpack / TypeScript の品質ゲートが揃っている）
> **前フェーズ**：[Backend レイヤ分割フェーズ](./05-backend-layers.md)
>
> **本フェーズの位置付け**：[README.md: 役割別 setup の後段](./README.md#役割別-setup-の後段レイヤ分割フェーズ) を参照。言語ツーリングが整った上に、その言語側でプロジェクト固有のレイヤ分割を確定するフェーズで、「悩む余地のない基本構造」とは別物として扱う。
>
> **書き方の方針**：本フェーズは依存ライブラリのインストールを伴わないため、役割別フェーズの「環境構築 + 品質ゲート 5 ステップ」パターンには載らない。代わりに「**決定値の確認 → ディレクトリ作成 → 各レイヤ README → 全体 README → rules ファイルに実装契約として固定 → 静的解析ツールの除外整合**」の構造で進める（Backend レイヤ分割フェーズと同パターン）。
>
> **本ファイルと `.claude/rules/frontend.md` の役割分担**：本ファイルが「**手順 + このフェーズで下す決定**」の SSoT、`frontend.md` が「**実装契約（R1 以降の機能実装が読む規約）**」の SSoT。`§決定値` の表は両ファイルに同じ値を書く（本ファイル＝決定の根拠と手順、frontend.md＝Claude 自動 load 用の機械可読契約）。一方を更新したら他方も合わせて更新する。

---

## 自律実行ポリシー（Claude が本ファイルを読んで作業する時の前提）

本ファイルは Claude に**そのまま実行を依頼**する想定で書かれている。次の原則を守って、ユーザーに確認を取らずに最後まで進める。

1. **ユーザーに設計上の確認を求めない**：`§決定値` に書かれた選択（生成物の置き場 / `lib/` のサブ構成 / README の粒度 / 命名規則 等）は**決定済みで議論しない**。関連 ADR や axon 等の他リポジトリ参照も既に消化済みのため、再検討しない。
2. **関連ファイルが本ファイルとズレていたら、関連ファイル側を直す**：以下のファイル群が `§決定値` と違う状態にあれば、本ファイルを真として書き換える。本ファイルを書き換える方向には進まない（本ファイルが SSoT のため）：
   - `apps/web/src/` 配下のフォルダ・README（15 個、§A のツリーに対応）
   - `.claude/rules/frontend.md`（フロント全般の実装契約）
   - `.claude/rules/frontend-component.md`（コンポーネント単位の実装契約、本ファイル §E + §G を機械可読版にしたもの）
   - `.claude/rules/frontend-hooks.md`（フック単位の実装契約、本ファイル §F + §G を機械可読版にしたもの）
   - `.claude/CLAUDE.md`（「ルールファイルの管理」リストに上記 3 ファイルが列挙されていること）
   - `apps/web/biome.jsonc` / `apps/web/knip.config.ts`（生成物パスの除外設定）
   - `docs/requirements/5-roadmap/01-roadmap.md`（R0-6 行の状態列とリンク列）
3. **新規ブランチを切ってから作業する**：[CLAUDE.md: ブランチ運用](../../../../.claude/CLAUDE.md#ブランチ運用) に従い、`feature/web/r0-6-app-directory-skeleton`（または同等の `feature/web/<名前>`）で作業する。`main` で直接作業しない。
4. **コミット・PR 作成は明示指示があるまで行わない**：[CLAUDE.md: Git 操作の禁止](../../../../.claude/CLAUDE.md#git-操作の禁止) に従い、`git add` / `git commit` / `git push` / PR 作成はユーザーから明示指示が出るまで保留する。ファイル作成・編集は自動で進めてよい。
5. **初期状態のばらつきに対する方針**：
   - 想定フォルダが存在しない → 作る
   - 想定フォルダが存在し中身が空 → README を入れる
   - 想定フォルダが存在し中身がある → 中身を確認して `§決定値` と矛盾する部分のみ書き換える。**生成物（`__generated__/api/`、旧 `lib/api/generated/` 等）は再生成可能なので削除して `mise run web:types-gen` で再構築**してよい。手書きの差分があれば内容を確認した上で取り込む
   - `.claude/rules/frontend.md` に旧セクション（旧 §型の命名規則 / 旧 §コーディングルール内の `index.ts` 禁止条項 等）が残っている → §決定値 / §C / §D を実装契約セクション側に集約し、旧セクションを刈り込む（手順 4-1 が SSoT）
   - `.claude/rules/frontend-component.md` が存在しない、または `§E` と矛盾する → §E を機械可読版に展開して作成 or 書き換える（手順 4-2 が SSoT）
   - `.claude/rules/frontend-hooks.md` が存在しない、または `§F` と矛盾する → §F を機械可読版に展開して作成 or 書き換える（手順 4-3 が SSoT）
   - `.claude/CLAUDE.md` の「ルールファイルの管理」リストに 3 ファイル（`frontend.md` / `frontend-component.md` / `frontend-hooks.md`）が揃っていない → 追加する
   - `apps/web/biome.jsonc` / `apps/web/knip.config.ts` に旧パス（`src/app/__generated__` / `src/lib/api/**`）が残っている → §A の `src/__generated__/` に揃える（手順 5 が SSoT）
6. **完了後に検証コマンドを必ず流す**：`mise run web:lint` / `mise run web:typecheck` / `mise run web:knip` を順に実行し、3 つすべて clean になることを確認する。失敗があれば修正して再実行（ユーザーに投げ返さない）
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
apps/web/src/
├── app/                            # Next.js App Router（既存、Next.js 規約）
├── components/                     # 複数ページで使い回す画面部品
│   ├── ui/                         # shadcn/ui 由来の汎用 UI（ドメイン語彙なし、lint 切る）
│   ├── parts/                      # ドメイン語彙を含む再利用ブロック（problem-card 等）
│   └── providers/                  # React の Provider 群（QueryClient / ApiError / Theme）
├── hooks/                          # 複数ページで使い回すカスタムフック（use-*）
├── lib/                            # React / Next.js 非依存の素のロジック・設定
│   ├── api/                        # 手書きの API ラッパ（error interceptor 等。生成物は __generated__/api/）
│   ├── validation/                 # Zod スキーマ（フォーム入力検証）
│   ├── utils/                      # 汎用関数（純粋関数、テスト容易）
│   ├── constants/                  # サイト全体の定数（ルートパス / 列挙ラベル / 既定値）
│   ├── styles/                     # 構造化スタイル（CodeMirror テーマ等、Tailwind で表現できないもの）
│   └── shared-query/               # TanStack Query の QueryClient + 既定 options
└── __generated__/                  # 自動生成物（人手で編集しない）
    └── api/                        # Hey API output（apps/api/openapi.json → TS / Zod / HTTP）
```

> `lib/utils.ts`（lib 直下の単発ファイル）：shadcn/ui の `cn()` ヘルパー等、1 行小物は無理にフォルダ化せず `lib/utils.ts` に直接置いてよい。

### B. 配置に関する重要な選択（なぜそうしたか）

| 論点 | 採用 | 不採用 | 採用理由 |
|---|---|---|---|
| 生成物の置き場 | `src/__generated__/api/` | `src/lib/api/generated/`（axon パターン） | grep / lint 除外 / Biome 除外 / Knip 除外 を **単一パス**で扱える。手書きラッパ（`lib/api/`）と生成物の境界が一目で分かる |
| `lib/` 配下のサブ構成 | `{api, validation, utils, constants, styles, shared-query}` 6 個 | 必要時に増やす遅延構成 | axon を参考に、想定ユースケースを最初から枠だけ用意。空フォルダでも README で意図を示すことで、R1 以降の実装者が「どこに置くか」で悩まなくなる |
| README の粒度 | **トップ + 全サブフォルダ**（合計 15 個：`src/` 1 + トップ 4 + サブ 10） | トップ + 直下フォルダのみ（5 個） | 初学者が階層を辿る時に「このフォルダ何？」で迷わない。空フォルダ防止の `.gitkeep` も README が兼ねる |
| 単発ファイル容認 | `lib/utils.ts` のような lib 直下の `.ts` を許容 | フォルダ化必須 | shadcn 規約の `cn()` ヘルパー等、1 行小物にフォルダを切るのは過剰 |

### C. レイヤ間の import 方向

| レイヤ | import してよい | import 禁止 |
|---|---|---|
| `app/` | `components` / `hooks` / `lib` / `__generated__` | （上位なし） |
| `components/` | 他の `components` / `hooks` / `lib` / `__generated__` | `app` |
| `hooks/` | 他の `hooks` / `lib` / `__generated__` | `app` / `components` |
| `lib/` | 他の `lib` / `__generated__` | `app` / `components` / `hooks`（React 非依存に保つ） |
| `__generated__/` | （何も import しない、終端） | 全て |

**補足ルール**：

- 依存は一方向。A → B かつ B → A の循環を作らない。`components/parts/` 内・`hooks/` 内など同レイヤの兄弟も同じ
- `__generated__/` を終端に保つ。手書きの interceptor / エラー解釈は `lib/api/` 側に被せる（[ADR 0006](../../../adr/0006-json-schema-as-single-source-of-truth.md)）
- `lib/` を React 非依存に保つ。`useState` / `useEffect` / JSX を含む実装は `hooks/` か `components/` に置く
- ページ固有部品は `app/.../page-dir/_components/` 等のコロケーション。複数ページで使うようになってから `src/components/` に昇格する（YAGNI）
- `index.ts` 再エクスポート禁止（バレル禁止）。例外：`__generated__/api/` 配下（Hey API が自動生成するため）

### D. 命名規則

| 種別 | 命名パターン | 例 |
|---|---|---|
| ファイル名・ディレクトリ名 | ケバブケース | `use-get-problems.ts` / `problem-card/` |
| React コンポーネント | PascalCase | `ProblemCard` / `DifficultyBadge` |
| 関数・変数 | camelCase | `formatDate` / `queryClient` |
| 定数 | SCREAMING_SNAKE_CASE | `DIFFICULTY_LABELS` / `MAX_PAGE_SIZE` |
| 一般的な型 | `◯◯Type` | `ProblemType` / `SubmissionType` |
| コンポーネントの props | `◯◯Props` | `ProblemCardProps` / `ButtonProps` |
| フックの戻り値型 | `◯◯Return` | `UseGetProblemsReturn` |
| RHF フォームの値型 | `◯◯FormValues` | `LoginFormValues` |
| Zod スキーマ変数 | `<formName>Schema` | `loginFormSchema` |
| フック名（CRUD 対応） | `useGet*` / `usePost*` / `usePatch*` / `useDelete*` | `useGetProblems` / `usePostSubmission` |
| フック名（UI 状態） | `use*` | `useDebounce` / `useHoverPopover` |

### E. コンポーネントの追加ルール（フォルダ化・名前一意・テスト/Storybook 同居の適用範囲）

`apps/web/src/` 配下に置く React コンポーネント（`components/{ui,parts,providers}/`、各ページの `_components/`、各コンポーネントの内部 `_components/`）に共通で適用する追加規約。詳細・コード例・shadcn 取り扱い手順は [.claude/rules/frontend-component.md](../../../../.claude/rules/frontend-component.md) が機械可読版 SSoT。

#### E-1. 全コンポーネントは同名フォルダで包む

`<name>/<name>.tsx` 形式。単一ファイル配置（`button.tsx`）は禁止。`src/components/` と各 `_components/` のどちらでも適用される。

- ✅ `components/ui/button/button.tsx`
- ✅ `app/(authed)/problems/[id]/_components/code-editor/code-editor.tsx`
- ❌ `components/ui/button.tsx`（単一ファイル禁止）

理由：テスト（`button.test.tsx`）・Storybook（`button.stories.tsx`）・内部 `_components/` `_hooks/` をコンポーネント本体と同じ単位で grep / 移動 / 削除できるようにするため。shadcn/ui の `pnpm dlx shadcn add` は単一ファイル出力なので、生成直後に同名フォルダへリネームする。

#### E-2. コンポーネント名はプロジェクト内でグローバル一意

`apps/web/src/` 配下の全コンポーネント（`components/` / 各ページの `_components/` / 内部 `_components/`）で **同名のコンポーネントを 2 つ以上作らない**。識別子（`export const Xxx`）もフォルダ名も含めて重複させない。

理由：Storybook の `meta.title` 衝突 / IDE 自動補完の曖昧化 / grep / リファクタが追えなくなる。

重複しそうな時はドメイン語彙を付ける：

- ❌ `ui/button/button.tsx` と `parts/button/button.tsx` を両方作る
- ✅ `ui/button/button.tsx`（汎用）と `parts/submit-button/submit-button.tsx`（解答送信専用）

既存名のチェック：

```bash
grep -r "export const Foo " apps/web/src/    # 識別子（PascalCase）
find apps/web/src -type d -name "foo"        # フォルダ名（kebab-case）
```

#### E-3. テスト・Storybook 同居の適用範囲（場所による差分）

`§E-1` のフォルダ化と `§E-2` の名前一意性は全ての場所で必須。違うのは **テスト / Storybook 同居の期待度**だけ：

| 配置場所 | テスト（`.test.tsx`） | Storybook（`.stories.tsx`） |
|---|---|---|
| `src/components/{ui,parts,providers}/<name>/`（共有） | UI ロジックがあれば **必須** | `parts/` 推奨、`ui/` `providers/` 任意 |
| `app/.../_components/<name>/`（ページローカル） | **任意** | **任意**（基本不要） |
| `<component>/_components/<sub>/`（内部部品） | **任意** | **任意** |

---

### F. フックの追加ルール（配置の選択・名前一意）

`apps/web/src/` 配下のカスタムフック（`hooks/`、各ページの `_hooks/`、各コンポーネントの `_hooks/`）に適用する追加規約。詳細・コード例は [.claude/rules/frontend-hooks.md](../../../../.claude/rules/frontend-hooks.md) が機械可読版 SSoT。

#### F-1. フックの配置（1 ファイル直置き or 同名フォルダを選べる）

コンポーネントとは違い、フックは JSX を返さずテスト 1 本で十分なケースが多いため、1 ファイル直置きを許容する。内部にサブフック・専用ユーティリティ・テストが必要になった時点で同名フォルダにリネームする。

- ✅ `hooks/use-debounce.ts`（1 ファイルだけ、テストもない）
- ✅ `hooks/use-get-problems/use-get-problems.ts` + `use-get-problems.test.ts` + 内部 `_hooks/`
- ❌ `hooks/use-debounce/use-debounce.ts`（中身がフック本体だけ、フォルダ化が過剰）

判断基準：「同フォルダ内に置きたい兄弟ファイル（テスト・型・内部フック）が 1 つでもあるか」。

#### F-2. フック名はプロジェクト内でグローバル一意

`apps/web/src/` 配下の全フック（`src/hooks/`、各ページの `_hooks/`、各コンポーネントの `_hooks/`）で **同名のフックを 2 つ以上作らない**。識別子（`export const useXxx`）もファイル名・フォルダ名も含めて重複させない。

理由：IDE 自動補完の曖昧化 / grep / リファクタが追えなくなる / 後で共有層に昇格させる時に名前衝突が起きる。

重複しそうな時はドメイン語彙・対象・粒度を付ける：

- ❌ ページ A `_hooks/use-form-state/` とページ B `_hooks/use-form-state/` を両方作る
- ✅ ページ A は `_hooks/use-login-form-state/`、ページ B は `_hooks/use-answer-form-state/`

既存名のチェック：

```bash
grep -r "export const useFoo " apps/web/src/   # 識別子（camelCase）
find apps/web/src -name "use-foo*"             # ファイル名 / フォルダ名（kebab-case）
```

---

### G. 「やってはいけないこと」（NG パターン一覧）

`src/README.md` および `frontend.md` の OK/NG コード片で取り上げる代表 NG。各 README は本リストから該当する項目を 3〜4 件抜粋して転記する。

#### G-1. 配置・import の NG

1. `hooks/` から `components/` を import（フックは JSX を返さない、`§C`）
2. `lib/` から `react` / `components/` / `hooks/` を import（lib は React 非依存、`§C`）
3. `__generated__/` から `src/` 配下を import（終端違反、`§C`）
4. ページ 1 つでしか使わない部品を `src/components/` に置く（コロケーションを使う）
5. `index.ts` で再エクスポートして `from "@/components/parts"` のように呼ぶ（バレル禁止、`§C`）
6. `services/` → `routers/` のような逆流的構造を Frontend で再現する（上位→下位の一方向、`§C`）

#### G-2. コンポーネント単位の NG

7. コンポーネントを単一ファイル配置（`button.tsx` のまま、`§E-1` 違反）
8. 同名のコンポーネントを 2 つ以上作る（`§E-2` 違反）
9. `export default ComponentName;`（名前付き export を使う）
10. `__generated__/api/` を直接 import（API は `hooks/use-*` 経由で呼ぶ）

#### G-3. フック単位の NG

11. 同名のフックを 2 つ以上作る（`§F-2` 違反）
12. `export default useFoo;`（名前付き export を使う）
13. 条件分岐の中で React のフック（`useState` / `useEffect` 等）を呼ぶ（React のルール違反）
14. サーバー状態（API レスポンス）を `useState` で長期保持する（TanStack Query 等に任せる）
15. 手書きの `fetch` / `axios` を使う（`__generated__/api/` の生成クライアントを使う）

---

## 1. ディレクトリ構造の最終状態

**目的**：`apps/web/src/` 配下に Frontend のレイヤを 1 つの方針で固定する。以降の機能実装はこの 4 系統（`components` / `hooks` / `lib` / `__generated__`）のどこに置くかを判断するだけ、という状態を作る。

**最終状態**（§自律実行ポリシー §7 の通り、初期状態のばらつきは問わない）：

- `apps/web/src/` 配下が §A のツリーに一致している：
  - トップ 4 系統が存在する：`components/` / `hooks/` / `lib/` / `__generated__/`（`app/` は Next.js 規約による既存ディレクトリで、本フェーズでは触れない）
  - サブ 10 ディレクトリが存在する：`components/{ui, parts, providers}/` + `lib/{api, validation, utils, constants, styles, shared-query}/` + `__generated__/api/`
- **計 15 個の `README.md` ファイル**が存在する：
  - `apps/web/src/README.md`（1 個、src/ 直下）
  - 上記 14 ディレクトリそれぞれに `README.md`（14 個）
  - 中身は手順 2 / 手順 3 で作る。本手順 1 の段階では空ファイルでもよい（最終的に手順 2 / 3 で書き込めば OK）
- `.gitkeep` ファイルが残っていない（README が空フォルダ防止を兼ねるため、`.gitkeep` は不要）
- §A のツリーに無い別のフォルダ（例：`src/lib/api/generated/` のような別配置）が残っていない

**完了基準**：

- 上記 15 個の README.md が（空でも可）存在する
- 14 ディレクトリすべてが空ではない（README 入り）
- `mise run web:dev` / `mise run web:lint` / `mise run web:typecheck` / `mise run web:knip` が clean で通る
- 既存テスト（あれば）が引き続き通る

**関連 ADR**：[ADR 0006](../../../adr/0006-json-schema-as-single-source-of-truth.md)（Pydantic SSoT → Hey API で TS 展開、`__generated__/api/` 配置確定）/ [ADR 0015](../../../adr/0015-codemirror-over-monaco.md)（CodeMirror 採用、`lib/styles/` の代表ユースケース）/ [ADR 0021](../../../adr/0021-r0-tooling-discipline.md)（Knip / Biome の R0 必須化、本フェーズで除外パスの整合を取る）/ [ADR 0036](../../../adr/0036-frontend-monorepo-pnpm-only.md)（pnpm workspaces 単一構成、`apps/web/` 配下に閉じる構造）

---

## 2. 各レイヤの README.md の最終状態

**目的**：各サブフォルダに人間向けの 1 ファイル README を置き、初学者が階層を辿る時に「このフォルダは何の置き場か」を即把握できるようにする。Backend レイヤ分割フェーズと同じ書き分け方針。

**最終状態**（全 README が下記の構成を満たす）：

各 README は以下のセクションを含む。すべてのフォルダで全セクション必須ではなく、必要なものを取捨選択する：

| セクション | 役目 | 必須か |
|---|---|---|
| `## <フォルダ名>/ とは何か` | そのフォルダが扱う仕組みと、比喩的な役割（汎用 UI / ドメイン部品 / 素のロジック / 自動生成物 等）を 1〜2 行で書く。`§A` のツリーコメントがそのまま叩き台 | 必須 |
| `## 役目` or `## ファイル配置` or `## 命名規則` | 代表パターン・配置例・命名対応表のうち必要なもの | 任意（取捨選択） |
| `## やってはいけないこと` | `§G` の NG パターン一覧から該当する項目を **2〜4 件**抜粋（コンポーネント系 README は `§G-1` + `§G-2`、フック系 README は `§G-1` + `§G-3`、`lib/` 系 README は `§G-1` を中心に。各 README の文脈に該当する NG が少ない場合は 1〜2 件でもよい） | 必須 |

**書き方の規約**：

- **コード片の扱い**：人間向けに概念ベースで書く。コード片は Claude 用 rules ファイル（`frontend.md` / `frontend-component.md` / `frontend-hooks.md`）に集約する。命名規則の具体例（Zod スキーマの型 export 等）が説明に必要な場合は短いコード片を含めてよい
- **専門用語の扱い**：[コメントスタイル](../../../../.claude/CLAUDE.md#コメントの書き方) に従い、SSoT / hydration / Server Component 等の専門用語は使わず平易な日本語で書く

**最終状態で存在すべき README**（全 15 ファイル）：

| パス | 重視する内容 |
|---|---|
| `apps/web/src/README.md` | トップの全体図（手順 3 で詳述） |
| `apps/web/src/components/README.md` | `ui/` `parts/` `providers/` の使い分け対比表 |
| `apps/web/src/components/{ui,parts,providers}/README.md`（3 ファイル） | それぞれの「とは何か」「役目」「やってはいけないこと」 |
| `apps/web/src/hooks/README.md` | 命名規則表（`useGet*` / `usePost*` 等）+ フック名グローバル一意性 |
| `apps/web/src/lib/README.md` | 6 サブの対比表 + `utils.ts` 例外の説明 |
| `apps/web/src/lib/{api,validation,utils,constants,styles,shared-query}/README.md`（6 ファイル） | それぞれの代表パターン |
| `apps/web/src/__generated__/README.md` | 再生成コマンドと「手で編集しない」原則 |
| `apps/web/src/__generated__/api/README.md` | Hey API output の役目 |

> `app/` 配下の README は本フェーズでは作らない（Next.js App Router は固有規約で動くため）。

**完了基準**：

- 上記 15 個の README.md が存在する
- 各 README は「とは何か」セクションを冒頭に持つ
- 紛らわしいレイヤ組（`lib/api/` と `__generated__/api/`、`components/ui/` と `components/parts/`、`lib/utils/` と `lib/utils.ts`）には対比的な記述がある
- 全 README で `§G` の NG パターンから該当する 1〜4 件が「やってはいけないこと」として転記されている（多すぎても少なすぎても可、文脈に該当するものを選ぶ）

---

## 3. `src/README.md` の最終状態

**目的**：人間が `apps/web/src/` 直下を開いた時に、レイヤ間の呼び出しの向きが 1 枚の図で見て取れる状態にする。

**最終状態**（`apps/web/src/README.md` が下記をすべて含む）：

A. **レイヤ一覧表**：トップ 5 系統（`app` / `components` / `hooks` / `lib` / `__generated__`）を「これは何か（役目）」付きで表にし、各セルから対応する README へリンクが張られている

B. **ASCII 図でレイヤ間の呼び出し方向**を示す。`§C` の import 方向と一致する：上から下に `app → {components, hooks, lib, __generated__}` → `components → {hooks, lib, __generated__}` → `hooks → {lib, __generated__}` → `lib → __generated__`。終端は `__generated__/`

   叩き台（実際の図は projects の `src/README.md` 内に書く）：
   ```text
   [ブラウザ画面] → app/ → {components, hooks, lib} → __generated__/api/
                                  ↓         ↓
                                  └→ hooks → lib → __generated__
   ```

C. **読み方の具体例**が含まれる：問題一覧画面が `components/parts/problem-card/` → `hooks/use-get-problems/` → `__generated__/api/` の順で呼ぶ典型フロー / `lib/` が React 非依存である意味 / `__generated__/` が終端である意味

D. **`## やってはいけないこと` セクション**が `§G` の NG パターン一覧から **6 件以上**を箇条書きで含む（`§G-1` 配置・import 系を中心に、コンポーネント・フック単位の重要 NG も含める）

**完了基準**：

- `apps/web/src/README.md` を開けば「何の機能がどう繋がるか」が図 + 補足で完結する
- 「やってはいけないこと」が `§G` から 6 件以上列挙されている
- 図中の矢印が `§C` の import 方向表と一致している

---

## 4. 実装契約を `.claude/rules/frontend{,-component,-hooks}.md` の 3 ファイルに固定

**目的**：Claude が新規実装時に参照する「実装契約」として、ディレクトリ配置 + import 方向 + 命名規則 + コンポーネント単位の配置 + フック単位の配置を、表 + コード片で曖昧さなく固定する。人間向け README が「概念で理解する」のに対し、rules ファイルは「パターンマッチで判定する」用途。

**役割分担（3 ファイル）**：

- [.claude/rules/frontend.md](../../../../.claude/rules/frontend.md) — ディレクトリ構成全体（5 系統 14 フォルダ）/ import 方向 / 命名規則 / コロケーション原則。**フロント全般**の実装契約
- [.claude/rules/frontend-component.md](../../../../.claude/rules/frontend-component.md) — `components/` と各 `_components/` 配下のコンポーネント 1 つの作り方。**フォルダ化必須**・**コンポーネント名のグローバル一意性**・テスト / Storybook（`src/components/` でのみ強い期待度）・shadcn 取り扱い
- [.claude/rules/frontend-hooks.md](../../../../.claude/rules/frontend-hooks.md) — `hooks/` と各 `_hooks/` 配下のフック 1 つの作り方。**フック名のグローバル一意性**・配置（直置き or フォルダ化を選べる）・テスト同居・`useGet*` / `usePost*` 等の命名・`isLoading` 初期値ルール

> **適用範囲の違い**：コンポーネントは `src/components/` と `_components/` の両方で**フォルダ化と一意性は必須**、テスト・Storybook の同居期待度だけ `src/components/` で強い。フックはすべての場所で**名前一意性は必須**、配置はテスト・サブフックの有無で 1 ファイル直置きか同名フォルダかを選べる。

### 4-1. `frontend.md` の最終状態

`§自律実行ポリシー §7` の通り、初期状態（既存セクションの有無 / 旧パス記載の有無 / 内容のズレ）は不問。**最終状態が下記の条件をすべて満たしていればよい**。既存セクションが条件と矛盾する場合は整合させ、無ければ追加し、すでに一致していれば何もしない。

A. **`## ディレクトリ構成（実装契約）` セクションが存在する**（または同等の包括セクションが 1 つ存在する）。内容は次を含む：
- `§A` のツリー（コメント付き）
- `§C` の import 方向表 + 補足ルール
- OK / NG コード片を 5 例以上（次の項目 B の具体例）
- `§D` の命名規則表
- `§E` / `§F` への参照（コンポーネント単位 → [.claude/rules/frontend-component.md](../../../../.claude/rules/frontend-component.md)、フック単位 → [.claude/rules/frontend-hooks.md](../../../../.claude/rules/frontend-hooks.md)）

B. **OK / NG コード片**が `.ts` コードブロックで以下 6 例以上含まれる：
- ✅ `page.tsx` が `@/components/parts/...` / `@/hooks/use-*` / `@/lib/constants/...` を呼ぶ
- ✅ 共有フックが `@/__generated__/api/client` と `@/lib/api/api-error-interceptor` を呼ぶ
- ❌ `hooks/` が `@/components/ui/button` を import
- ❌ `lib/` が `react` の `useState` / `@/components/...` を import
- ❌ `__generated__/api/` が `@/lib/...` を import
- ❌ `@/components/parts`（バレル経由）で import

C. **`§A` / `§C` / `§D` と重複する内容が他のセクションに残っていない**。実装契約セクション以外に、命名規則・配置規則・import 方向と被るものが見つかった場合は実装契約セクション側に統合する。代表例：
- 命名規則を独立した別セクション（例：`## 型の命名規則` のような）に持たせない（命名は `§D` の表 1 箇所に集約）
- 「`index.ts` 作成禁止」「再エクスポート禁止」「ケバブケース命名」を運用細則セクション（例：`## コーディングルール` のような）の主要トピックにしない。実装契約側に集約し、運用細則セクションは `cn()` 使用・class 文字列定数化・`useGet*` の `isLoading` 初期値など**実装契約に書けない細則だけ**を残す。運用細則セクション冒頭には「ファイル名・型名・`index.ts` 禁止は §ディレクトリ構成（実装契約）が SSoT」のリードを置く

> フレッシュ・スタート（既存 `frontend.md` に上記のような重複セクションが**そもそも存在しない**）なら、この条件 C は何もせずに満たされる（§自律実行ポリシー §7）。

D. **`@/` エイリアスの説明セクション**（例：`## importパスの規則`）が `@/__generated__/api/*` の例を含んでいる（古い `@/lib/api/generated/*` の例は載っていない）

E. **コロケーション関連セクション**（例：`## コロケーション原則` 内の `## ファイル配置`）が以下の対比を含む：
- コンポーネント（`.tsx`）：**必ず同名フォルダ + 同名ファイル**で配置（単一ファイル禁止）
- フック（`.ts`）：1 ファイル直置きと同名フォルダを選べる

F. **API クライアントセクション**（例：`## API クライアント`）の生成物パスが `apps/web/src/__generated__/api/` に揃っている（旧 `apps/web/src/lib/api/generated/` への言及が残っていない）。あわせて「生成物には手を入れず、横断処理は `src/lib/api/` 側で被せる」一文が含まれる

> **書き換え方の指針**：上記の「**最終的にこうなっていればよい**」を満たすために、既存ファイルから関連箇所を探して整合させる。一致しているものは触らない、無いものは足す、矛盾しているものは書き換える（§自律実行ポリシー §7）。

### 4-2. `.claude/rules/frontend-component.md` の最終状態

**最終状態**：

- ファイルが存在する：`.claude/rules/frontend-component.md`
- frontmatter `paths:` に `apps/web/src/components/**` と `apps/web/src/app/**/_components/**` が含まれる（Claude が該当ファイル編集時に自動 load する）
- 冒頭に **「適用範囲（場所による差分）」表**が存在し、`src/components/` と `_components/` で違うのは **テスト・Storybook 同居の期待度のみ**（フォルダ化・名前一意性はどちらも必須）であることが明示されている
- 以下の章をすべて含む：

| 章 | 内容 |
|---|---|
| §1 全コンポーネントはフォルダで包む | `<name>/<name>.tsx` 形式必須、`src/components/` も `_components/` も同じ、shadcn 取り扱い手順 |
| §2 コンポーネント名はグローバル一意 | `apps/web/src/` 配下の全コンポーネント（`components/` / 各 `_components/` / 内部 `_components/`）で同名禁止。重複時のドメイン語彙の付け方、既存名のチェック手順（`grep` / `find` 例）を含む |
| §3 コンポーネントフォルダの中身 | 本体 / `.test.tsx` / `.stories.tsx` / `types.ts` / `_components/` / `_hooks/` / `_constants/` / `_utils/` の表。**`src/components/` での扱いと `_components/` での扱いを別の列で書き分ける** |
| §4 コンポーネント本体の書き方 | 名前付き export、アロー関数、props 型のファイル冒頭宣言、`"use client"` の使い分け、サンプルコード |
| §5 テスト | Vitest + Testing Library + MSW、`userEvent`、日本語テスト名、サンプルコード。冒頭リードに「主に `src/components/`、`_components/` は任意」を明記 |
| §6 Storybook | `meta.title` は「フォルダ階層 / コンポーネント名」、画面で違いが見える代表ケースだけ、意味のあるラベル、サンプルコード。冒頭リードに「主に `src/components/parts/`、それ以外は任意」を明記 |
| §7 CSS / className | `cn()` 使用、重複クラスは定数化、サンプルコード |
| §8 やってはいけないこと | `§G` から該当する NG を抜粋（単一ファイル配置 / 同名コンポーネントの作成 / `export default` / `Story1` 等の番号 / コンポーネント内サーバー状態保持 / `fireEvent` 等） |

### 4-3. `.claude/rules/frontend-hooks.md` の最終状態

**最終状態**：

- ファイルが存在する：`.claude/rules/frontend-hooks.md`
- frontmatter `paths:` に `apps/web/src/hooks/**`、`apps/web/src/app/**/_hooks/**`、`apps/web/src/components/**/_hooks/**` が含まれる
- 以下の章をすべて含む：

| 章 | 内容 |
|---|---|
| §1 フックの配置（1 ファイル直置き or 同名フォルダを選べる） | JSX を返さないためコンポーネントより緩い。判断基準は「同フォルダ内に置きたい兄弟ファイルが 1 つでもあるか」 |
| §2 フック名はプロジェクト内でグローバル一意 | `hooks/` と各 `_hooks/` 配下を含めて同名禁止。重複時のドメイン語彙の付け方、既存名のチェック手順（`grep` / `find` 例） |
| §3 フックフォルダの中身（フォルダ化した時） | `<name>.ts` / `.test.ts` / `types.ts` / `_hooks/` / `_utils/` / `_constants/` の表。`.stories` は無い（フックは画面を描画しない） |
| §4 フック本体の書き方 | 名前付き export、アロー関数、戻り値型 `UseXxxReturn`、`useGet*` / `usePost*` / `usePatch*` / `useDelete*` / `use*` の命名表、`isLoading` 初期値ルール、API は `__generated__/api/` 経由、サンプルコード |
| §5 テスト | Vitest + Testing Library の `renderHook`、MSW モック、`waitFor`、日本語テスト名、サンプルコード |
| §6 やってはいけないこと | `§G` から該当する NG を抜粋（`hooks/` から `components/` import / 同名フック作成 / `export default` / 条件分岐内のフック呼び出し / サーバー状態の `useState` 長期保持 / 手書き `fetch` / ページ専用フックの `src/hooks/` 配置） |

### 4-4. 共通の最終状態

- 上記 3 ファイル（`frontend.md` / `frontend-component.md` / `frontend-hooks.md`）が [claude-rules-authoring.md](../../../../.claude/rules/claude-rules-authoring.md) の書き方規約に従っている（リンクではなく直接記載、表 / 箇条書きで列挙、本拠地がある場合は冒頭でリードを付ける）
- `.claude/CLAUDE.md` の「ルールファイルの管理」リストに上記 3 ファイルすべてが列挙されている

**完了基準**：

- `frontend.md` の「§ディレクトリ構成（実装契約）」セクションに `§A` のツリー + `§C` の import 方向表 + OK/NG 例 + `§D` の命名規則表 + `frontend-component.md` / `frontend-hooks.md` への参照が揃っている
- `frontend-component.md` に §1〜§8 + 適用範囲表（`src/components/` と `_components/` の test/story 期待度差分）が揃っている
- `frontend-hooks.md` に §1〜§6 + フック命名表（CRUD / UI 状態）が揃っている
- import 方向表に 5 レイヤすべてが行として並ぶ
- 既存の重複（旧 §型の命名規則 / §コーディングルール内の `index.ts` 禁止条項 / §コロケーション原則 §ファイル配置の単一ファイル可表現）は実装契約セクション側に統合され、旧セクションには運用細則のみ残る
- `CLAUDE.md` の「ルールファイルの管理」リストに `frontend-component.md` と `frontend-hooks.md` が追加されている

---

## 5. 設定ファイルの整合（biome / knip）

**目的**：手順 1〜4 で確定した `__generated__/api/` 配置を、静的解析ツールの除外パスにも反映する。`biome.jsonc` / `knip.config.ts` が古いパス（`src/app/__generated__` / `src/lib/api/**` 等）を参照していると、生成物が増えた時に CI で誤検知が出る。

**最終状態**（§自律実行ポリシー §7 の通り、初期状態のばらつきは不問）：

1. **[apps/web/biome.jsonc](../../../../apps/web/biome.jsonc) の最終状態**：
   - `files.includes` 配列に `!src/__generated__` が含まれる（生成物全体を Biome の走査から除外）
   - `overrides` に **`src/__generated__/**` を対象とする lint / format 無効化エントリ**が存在する（生成コードを書き戻さないため）
   - 旧パスの言及（`src/app/__generated__` / `src/lib/api/generated` 等）が残っていない
   - インラインコメントが新パスに整合している
2. **[apps/web/knip.config.ts](../../../../apps/web/knip.config.ts) の最終状態**：
   - `ignore` 配列に `src/__generated__/**` が含まれる
   - `ignore` 配列に旧 `src/lib/api/**` が残っていない（`src/lib/api/` は手書きラッパ置き場になったため knip 解析対象に含める）
   - インラインコメントが新パスに整合している
3. **`.gitignore` は変更しない**：生成物は CI drift 検出のため Git 管理下に置く方針（[ADR 0006](../../../adr/0006-json-schema-as-single-source-of-truth.md)）

> **想定される初期状態のばらつき**：（a）旧パス（`src/app/__generated__` 等）が記載済 → 新パスに置換、（b）何も書かれていない（フレッシュ） → 新パスを追加するだけ、（c）既に新パスが入っている → 何もしない。いずれの場合も最終状態は上記に一致させる。

**完了基準**：

- `mise run web:lint` / `mise run web:typecheck` / `mise run web:knip` が clean で通る
- 設定ファイル内の生成物パス言及が `src/__generated__/api/` に揃っている
- 設定ファイル内の旧パス（`src/app/__generated__` / `src/lib/api/**` / `src/lib/api/generated`）が残っていない：
  ```bash
  grep -E 'src/app/__generated__|src/lib/api/\*\*|src/lib/api/generated' apps/web/biome.jsonc apps/web/knip.config.ts
  # 何もマッチしなければ OK
  ```

---

## 6. 進捗トラッカーへの反映の最終状態

**目的**：本フェーズが終わったことを、プロジェクトの進捗管理仕組み（ロードマップ / プロジェクト管理ツール / README 等）に反映する。

**最終状態**：

- **プロジェクトの進捗トラッカー**（このプロジェクトでは [docs/requirements/5-roadmap/01-roadmap.md](../01-roadmap.md)。別プロジェクトでは GitHub Project / Notion / README 等、各プロジェクトの慣習に従う）で、本フェーズに該当する項目が**完了状態**として記録されている
- 進捗トラッカー上の該当エントリから、**本ファイル**（または同等の手順詳細）への**リンク**が辿れる
- 本ファイル冒頭のステータスマーク（`# 06. Frontend レイヤ分割（✅ 完了）` の `✅`）が完了状態を示している

> **このプロジェクトでの具体例**：[01-roadmap.md](../01-roadmap.md) の R0-6 行が、状態列 `✅ 完了` + 詳細手順列が本ファイルへのリンク `[r0-setup/06-frontend-layers.md](./r0-setup/06-frontend-layers.md)` になっている状態。古い表現（`🔴 未着手` / 未着手プレースホルダ / 旧リンク等）が残っていれば最終状態に合わせる。

**完了基準**：

- 進捗トラッカー上で本フェーズが完了になっている
- 本ファイルへのリンクが進捗トラッカーから辿れる
- 本ファイル冒頭のステータスマークが完了状態（`✅`）になっている

---

## 関連

- 親階層：[README.md: 役割別 setup の後段](./README.md#役割別-setup-の後段レイヤ分割フェーズ)
- 前フェーズ：[05-backend-layers.md](./05-backend-layers.md)
- ロードマップ：[01-roadmap.md: Now：R0 基盤](../01-roadmap.md#nowr0-基盤直列初期慣行--役割別環境構築--レイヤ分割--mcp-整備)
- 実装契約 SSoT：[.claude/rules/frontend.md](../../../../.claude/rules/frontend.md)
- 人間向けレイヤ概要：[apps/web/src/README.md](../../../../apps/web/src/README.md)
- 関連 ADR：[ADR 0006](../../../adr/0006-json-schema-as-single-source-of-truth.md)（Pydantic → Hey API → TS、`__generated__/api/` 配置の根拠）/ [ADR 0015](../../../adr/0015-codemirror-over-monaco.md)（CodeMirror、`lib/styles/` の代表ユースケース）/ [ADR 0021](../../../adr/0021-r0-tooling-discipline.md)（R0 必須補完ツール、本フェーズで除外パスの整合を取る）/ [ADR 0036](../../../adr/0036-frontend-monorepo-pnpm-only.md)（pnpm workspaces 単一構成）
