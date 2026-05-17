---
name: pr-review-by-commit
description: GitHub PR をコミット単位で網羅レビューし、工数無視で純粋なメリット観点から「対応すべき」/「対応不要」に仕分ける
argument-hint: "<PR URL または PR 番号>"
---

# PR コミット別レビュー（純メリット仕分け）

引数 `$ARGUMENTS` を PR URL または PR 番号として解釈する。

## このスキルの方針

- **コミット単位**で全部見る（PR 全体 diff をぼんやり眺めるのではなく、1 コミットずつ意図と差分を突き合わせる）
- **指摘事項は数を絞らない**：気付いたものは全部書く
- **工数を「対応すべきかの判断軸」に入れない**：判断は純粋なメリット / デメリットのみ。「対応コストが高いから対応不要」は禁止
- **工数推定は記載してよい**：参考情報として「概算: 30 分 / 半日 / 1 日」のような目安は出力に含めて良い。ただし優先度・仕分けの根拠にはしない
- **PR スコープ内 / 外を判定する**：各指摘に対して、PR のビジネス要件範囲内かどうかを明示する
  - スコープ内：本 PR の概要 / コミットメッセージ / 関連要件 .md で宣言された範囲に含まれる
  - スコープ外：宣言された範囲外（例：認証 PR でフロントエンド実装が未着手、別 PR 予定と明記されている等）
- 各指摘を **「対応すべき」/「対応不要」** の二択に仕分ける（曖昧な「nice to have」は作らない）
- 最後に **優先度高 / 中 / 不要** で総括する

## 手順

### 1. PR の取得

```bash
gh pr view <番号> --repo <owner>/<repo>
gh pr view <番号> --repo <owner>/<repo> --json commits --jq '.commits[] | "\(.oid[:8]) \(.messageHeadline)"'
```

- PR 概要（タイトル / 本文 / additions / deletions）を読み、対象スコープを把握
- コミット一覧（時系列）を取得して N 件あるか確認
- N が 15 件超の場合はユーザーに **「全件レビューでよいか」確認** する（context 消費が大きいため）

### 2. 各コミットの diff を取得

ローカルにブランチがあるなら `git show <sha>` を優先（`gh pr diff` は PR 全体しか取れない）。

```bash
# 4 件まとめて並列取得（context 効率化）
git show <sha1> --stat --format=fuller
git show <sha2> --stat --format=fuller
...
```

- `--stat --format=fuller` で **変更ファイル一覧 + コミットメッセージ全文** を見る
- 大きな差分は別途 `git show <sha> -- <path>` でファイル単位で読む
- 全 commits をまず stat レベルで把握 → 重要そうな実コードを `Read` で詳細確認

### 3. 関連コードと規約の読み込み

レビュー対象の正当性を判断するため、以下を併読：

- 該当 feature の要件 .md（`docs/requirements/4-features/<name>.md`）
- 該当 layer のルール（`.claude/rules/backend.md` / `frontend.md` / `worker.md` 等）
- 関連 ADR（コミットメッセージや要件から辿る）
- 既存テスト（`tests/` 配下）

「コードと規約のどちらが正か」を判断する根拠が無いと指摘が浅くなる。

### 4. 各コミットの指摘抽出

1 コミットごとに以下の観点でスキャンする。**まず変更ファイルの所属レイヤ**（Frontend / Backend / Worker / Infra / Docs）を特定し、**共通観点 + レイヤ別観点**の両方を当てる。

#### 共通観点（全レイヤ）

- **正確性**：バグ / 競合状態 / null 安全性 / 例外伝播の欠落 / 境界条件
- **セキュリティ**：秘密情報のログ漏洩 / 本番デフォルトの安全装置 / 改ざん検証 / インジェクション余地（SQL / コマンド / XSS / SSRF / オープンリダイレクト）
- **規約整合**：プロジェクトルール（`.claude/rules/`）/ ADR / 要件 .md との一致
- **設計**：レイヤ境界違反 / DRY 違反 / マジックナンバー / 名前の妥当性 / YAGNI 違反
- **パフォーマンス**：レイヤ別観点を参照
- **テスト容易性**：mockable か / 副作用が境界に閉じているか / 純粋関数に切り出せるか
- **保守性**：将来の拡張で破綻しないか / hardcode list の増殖 / コメントの陳腐化リスク
- **ドキュメント整合**：実装と requirements / ADR / CLAUDE.md / `.env.example` / README の drift
- **コミット粒度**：同 PR 内で「前の commit を覆す変更」がないか（純メリットでは無駄）

#### レイヤ別観点

**Backend（FastAPI / Python）** — 変更ファイルが `apps/api/` 配下にある場合
- レイヤ境界（Router → Service → Repository → ORM、ADR 0044）の import 方向違反
- Pydantic SSoT 違反（schemas 以外で型定義 / from_attributes / alias_generator）
- SQLAlchemy 2.0 async パターン違反（同期 API 混入、`Mapped[]` 不使用）
- トランザクション境界の置き場所（Service 層で `async with session.begin()`）
- DB クエリ N+1 / `selectinload` の不足 / `in_([])` の空ガード
- 認可チェック漏れ（「自分のリソースか」の where 条件）
- マイグレーション（autogenerate の限界 / `down_revision` / data migration 欠落）
- Redis / DB 重複問い合わせ / pipeline atomicity
- ruff / pyright / pip-audit / deptry の警告残り
- `Depends()` を default 引数に書く B008 違反

**Frontend（Next.js / TS）** — 変更ファイルが `apps/web/` 配下にある場合
- Server Component / Client Component の境界（`"use client"` の位置）
- hydration mismatch リスク（時刻 / 乱数 / ブラウザ API の SSR 直接利用）
- フォルダ構成 / 命名グローバル一意（`.claude/rules/frontend-component.md` / `frontend-hooks.md`）
- `useGet*` 命名 / `isLoading` 初期値 / コロケーション
- Hey API 生成型を直接編集していないか / 手書き fetch との二重実装
- アクセシビリティ（ラベル / ARIA / キーボード / フォーカス管理）
- パフォーマンス（不要 re-render / `useMemo` 誤用 / 巨大バンドル / next/image 不使用）
- セキュリティ（`dangerouslySetInnerHTML` / `target="_blank"` の `rel="noopener noreferrer"` / Cookie 属性）
- Biome / Knip / syncpack / `tsc --noEmit` の警告残り
- 国際化（日本語 hardcode）/ エラーバウンダリ

**Worker（Go）** — 変更ファイルが `apps/workers/<name>/` 配下にある場合
- `context.Context` の伝播（cancel / timeout が呼び出し連鎖の末端まで届くか）
- goroutine leak（起動した goroutine が停止条件を持つか）
- channel の close 責務 / nil channel
- `defer` の順序 / panic recovery / resource 解放
- error wrap（`fmt.Errorf("...: %w", err)`）/ sentinel error の使い分け
- ジョブ取得の `SELECT FOR UPDATE SKIP LOCKED` 契約（ADR 0046）/ 可視性タイムアウト / リトライ・DLQ
- 構造化ログ（`slog`）/ trace_id 連結（ADR 0010）
- LLM 呼び出しの timeout / retry / circuit breaker / コスト上限
- サンドボックス（Docker）リソース制限 / ネットワーク遮断
- `gofmt` / `golangci-lint` / `govulncheck` の警告残り

**Infra（Terraform）** — 変更ファイルが `infra/` 配下にある場合
- `terraform plan` 出力の破壊的変更（destroy / replace）
- IAM 権限の最小化（`*:*` 拒否 / 不要な `Action`）
- secrets の値を tfstate に直書きしていないか
- コスト影響（インスタンス種別 / 自動スケーリング上限）
- 障害ドメイン（マルチ AZ / バックアップ）
- ドリフト検知（手動変更を import せず apply で上書きしていないか）

**Docs** — 変更ファイルが `docs/` 配下にある場合
- 5 バケット構造（`.claude/rules/docs-rules.md`）の守備範囲違反
- 重複記述（SSoT 原則）/ 死リンク
- Mermaid アンチパターン（`<br/>` / dotted-arrow dot / 暗黙修飾子）
- ADR の Status 整合（Superseded / Accepted の本文書き換え運用）

#### 指摘の書き方

各指摘に通し番号を振り、以下を含める：

- **何が問題か**（1 行）
- **コード位置への markdown リンク**（`[ファイル名:行番号](relative/path#Lxx-Lyy)`）
- **理由 / 影響**（なぜ純メリットで対応すべきか、または不要か）
- **対応案**（あれば 1 行）
- **PR スコープ判定**：`[スコープ内]` または `[スコープ外: <理由>]` のタグを付ける
- **工数概算**（任意）：`(概算: 30 分)` のように軽く付記して良い。記載は参考情報で、対応判断には使わない

例：
```
- (40) [auth.py:100](apps/api/app/services/auth.py#L100) `logger.info(sid=%s)` で秘密情報の平文ログ漏洩 [スコープ内] (概算: 15 分)
  - 理由：ログ閲覧者がセッション乗っ取り可能。OWASP A09:2021 Logging Failures
  - 対応案：`sid[:8] + "..."` で prefix のみログ、または別途 trace_id 発行

- (76) テストファイルがゼロ [スコープ外: 本 PR 概要に「テストは別 PR `/backend-test authentication`」と明記] (概算: 1 日)
  - 理由：認証ロジックがテスト無しで main に入る
  - 対応案：本 PR にマージ前に最低限 service / cookies の unit test を追加するか、別 PR を必須化する
```

### 5. セキュリティ専用チェック（独立ステップ）

共通観点 / レイヤ別観点だけだと観察依存で抜け漏れが出る。OWASP Top 10 / ASVS をベースにした**フラットなチェックリスト**を別途回す。本ステップで見つけた指摘は重大度が高いことが多く、優先度高に倒すデフォルト。

#### A. 認証・セッション

- [ ] 秘密情報（password / API key / session ID / OAuth token / CSRF token / JWT）が **ログに平文で出ていない** か（`logger.info(..., sid=...)` 等）
- [ ] セッション ID / Cookie 値が CSPRNG（`secrets.token_urlsafe` / `crypto.randomBytes`）で発行されているか
- [ ] セッション固定攻撃（fixation）対策：ログイン成功時に **既存セッション ID を必ず再発行** しているか
- [ ] ログアウトでサーバ側セッションが確実に破棄されるか（Cookie クリアだけだと不十分）
- [ ] OAuth `state` パラメータが TTL + 1 回使い切りで CSRF 対策できているか
- [ ] OAuth `redirect_uri` がホワイトリスト固定か（動的構築は禁止）
- [ ] 認証失敗時のエラーメッセージが「ユーザー存在の有無」を漏らしていないか（user enumeration）
- [ ] レート制限がログイン / OTP / パスワード変更 / OAuth エンドポイントに掛かっているか

#### B. 認可（IDOR / 権限昇格）

- [ ] 「自分のリソースか」チェックが **全ての protected endpoint** に入っているか（where 条件 / Service 層ガード）
- [ ] 管理者専用エンドポイントが `Depends(get_current_admin)` 等で保護されているか
- [ ] パスパラメータ / クエリパラメータの ID を信用していないか（`/users/<id>/posts` の `<id>` 検証）
- [ ] バルク操作（`ids[]`）で他人の ID が混入しても弾けるか
- [ ] テナント分離（マルチテナント想定なら tenant_id where 条件）

#### C. 入力検証・インジェクション

- [ ] SQL：ORM パラメータ化 / `text(":id").bindparams(id=...)` を使っているか。`f"... {var} ..."` 等の文字列結合はゼロか
- [ ] コマンド：`subprocess.run(..., shell=False)` か。`shell=True` + 動的引数は禁止
- [ ] ファイルパス：path traversal（`../../etc/passwd`）対策。`Path(...).resolve().is_relative_to(base)` で正規化検証
- [ ] テンプレート：Jinja2 / EJS の autoescape が ON か。`| safe` / `dangerouslySetInnerHTML` の使用箇所を全件確認
- [ ] 正規表現：ReDoS 余地のあるパターン（ネスト量化子 / バックトラック爆発）がないか
- [ ] LDAP / XPath / NoSQL / GraphQL のクエリ組み立て

#### D. XSS / CSRF / クリックジャッキング

- [ ] React / Next.js：`dangerouslySetInnerHTML` の使用箇所と入力源
- [ ] URL を href に入れる箇所で `javascript:` スキームを弾いているか
- [ ] CSRF：状態変更系（POST/PUT/DELETE/PATCH）に CSRF 防御（double submit cookie / SameSite + Origin 検証）
- [ ] CSP / X-Frame-Options / Referrer-Policy / Permissions-Policy ヘッダー
- [ ] Cookie 属性：`HttpOnly` / `Secure` / `SameSite` / `Path` / `Domain` / `Max-Age` の一貫性
- [ ] `set_cookie` と `delete_cookie` の属性が一致しているか

#### E. SSRF / オープンリダイレクト

- [ ] 外部 URL を fetch する箇所でホワイトリスト / 内部 IP（127.0.0.1 / 169.254.169.254 / RFC1918）拒否
- [ ] リダイレクト先（`?next=` / `?return_to=` / `Location` ヘッダー）が同一オリジン相対パス縛り
- [ ] 画像 / アバター URL を proxy する経路で内部リソース取得が起きないか

#### F. シークレット管理

- [ ] `.env` / `.env.example` / `*.tfvars` がコミットされていないか
- [ ] ハードコードされた API key / password / private key（PEM）の検出
- [ ] 本番デフォルト値の安全装置：`dev-only-change-me` のようなプレースホルダで起動可能になっていないか（`ENV=production` + default 値拒否の validator）
- [ ] `COOKIE_SECURE=false` / `DEBUG=True` が本番で有効化されない仕組み
- [ ] tfstate / Docker image / ログ / エラー画面に secrets が漏れていないか

#### G. 暗号 / 署名

- [ ] 自前暗号実装がないか（標準ライブラリ / itsdangerous / cryptography に委譲）
- [ ] HMAC 比較で `hmac.compare_digest` / `crypto.timingSafeEqual` を使っているか（タイミング攻撃対策）
- [ ] パスワード保存：`bcrypt` / `argon2` / `scrypt`。`md5` / `sha1` / `sha256` 直書きは禁止
- [ ] JWT：`alg: none` 不許可 / 鍵ローテーション戦略
- [ ] TLS：自己署名証明書を本番で受容していないか（`verify=False` の検出）

#### H. レート制限・DoS

- [ ] レート制限が機能別に閾値設計されているか（`02-api-conventions.md` の表との整合）
- [ ] 重い処理（LLM 呼び出し / 採点 / 問題生成）に並行数制限 / コスト上限
- [ ] 巨大 payload の上限（`max_request_size` / Multer の limits）
- [ ] 正規表現 / JSON のネスト深さ制限

#### I. ファイルアップロード / ダウンロード

- [ ] ファイル種別検証（拡張子だけでなく magic byte / Content-Type）
- [ ] 保存パスのサニタイズ / UUID 付与
- [ ] ダウンロード時の `Content-Disposition` の `filename` エスケープ
- [ ] アンチウイルススキャン / サンドボックス実行

#### J. CORS / Origin

- [ ] `Access-Control-Allow-Origin: *` + `Allow-Credentials: true` の併用禁止
- [ ] 許可 origin がホワイトリスト固定で reflect 化していないか
- [ ] preflight でメソッド / ヘッダーが過剰許可されていないか

#### K. 依存関係 / サプライチェーン

- [ ] `pip-audit` / `npm audit` / `govulncheck` の警告が残っていないか
- [ ] 新規依存追加時にダウンロード数 / メンテナンス頻度 / ライセンスを確認したか
- [ ] lockfile（`uv.lock` / `pnpm-lock.yaml` / `go.sum`）がコミットされているか
- [ ] GitHub Actions の third-party action が SHA pin されているか（`@v3` ではなく `@<sha>`）

#### L. ログ / 観測性のセキュリティ

- [ ] 構造化ログに PII（メール / 氏名 / 電話 / IP）/ 秘密情報が出ていないか
- [ ] エラーログにスタックトレースを返してクライアントに見せていないか（本番）
- [ ] OpenTelemetry のスパン属性に秘密情報が乗っていないか

#### M. インフラ・コンテナ

- [ ] Docker image：root ユーザーで起動していないか（`USER nonroot`）
- [ ] サンドボックスコンテナ：network 遮断 / read-only filesystem / リソース制限
- [ ] Terraform：IAM `*:*` 拒否 / S3 bucket public access block / セキュリティグループの 0.0.0.0/0 開放
- [ ] secrets を環境変数で渡す経路の暗号化（AWS Secrets Manager / SSM Parameter Store）

#### 出力位置

セキュリティ指摘は **コミット別レビュー / 要件整合チェック / 全体横断のどれにも混ぜず、`## セキュリティチェック` 独立セクション** で出力する。重大度（Critical / High / Medium / Low）を必ず付ける：

```markdown
## セキュリティチェック

### Critical（マージ前必須）
- (40) [auth.py:100](path#L100) `logger.info("sid=%s", sid)` で平文ログ漏洩。ログ閲覧者がセッション乗っ取り可能 → `sid[:8]+"..."` に変更

### High（マージ前推奨）
- (4) [config.py:115](path#L115) `SESSION_SIGNING_SECRET` の default `"dev-only-change-me"` で本番起動可能 → `ENV=production` 時 default 拒否 validator 追加

### Medium / Low
- ...
```

### 6. 要件定義との整合チェック（独立ステップ）

コミット単位の指摘とは別軸で、**要件 SSoT に対する drift** を専用に洗う。本ステップは独立して実施する（コミット別レビューに埋もれさせない）。

#### チェック対象と方法

1. **要件 .md の受け入れ条件チェックリスト**（`docs/requirements/4-features/<name>.md` の「受け入れ条件」節）
   - チェック項目を 1 個ずつ実装と突き合わせる（`- [ ]` も `- [x]` も全部）
   - 「観測可能な振る舞い」として書かれた内容が、実装の挙動（API / DB / Redis / 画面遷移 / ジョブ処理結果）と一致するか
   - 一致しない項目は **「要件 .md を更新すべき」or「実装を直すべき」** のどちらかを明示

2. **要件 .md のステータス節**（`## ステータス` の `- [x]` / `- [ ]`）
   - PR でステータスを更新しているか
   - 「バックエンド実装完了 [x]」「フロントエンド実装完了 [x]」「Worker 実装完了 [x]」のチェックと実装の実態が一致するか

3. **ビジネスルール節**（`## ビジネスルール` / `§N.1 ビジネスルール`）
   - 1 ルールずつ、対応する実装箇所を指差し確認
   - 業務文（例：「複数セッション許容」「採点は 3 回平均」「問題は重複させない」）を **実コードのどの行で満たしているか** を答えられるか

4. **API / 画面 / フロー節**（変更レイヤに応じて）
   - Backend：要件の API 表 / JSON 例 / ステータスコードが `apps/api/openapi.json` と一致するか。302 redirect の Location / Set-Cookie がスキーマに表現されているか
   - Frontend：要件の画面・主要インタラクション・遷移先が実装と一致するか。Hey API 生成型を使っているか
   - Worker：要件のジョブフロー（投入 → 取得 → 処理 → 書き戻し）が ADR 0046 の配送保証契約と整合するか。プロンプト version が要件と一致するか

5. **バリデーション節**（`§N.5 バリデーション`）
   - 業務上のバリデーションルールが Backend / Frontend 両方で網羅されているか（片側だけだと迂回可能）
   - 機械的検証は Pydantic / Zod が SSoT、業務ルールは要件 .md が SSoT という分担が守られているか

6. **ADR との整合**
   - 要件 .md / コミットメッセージ / コメントで参照される ADR を **全部開いて** Decision 節と実装を突き合わせる
   - ADR が `Status: Accepted` のままで、実装がその Decision を覆していないか
   - ADR で「採用ライブラリ」と書かれているものが実際に使われているか（authlib drift のような例）

7. **`.claude/rules/` 規約との整合**
   - レイヤごとのルール（`backend.md` / `frontend.md` / `worker.md` / `alembic-sqlalchemy.md` / `prompts.md` / `claude-rules-authoring.md`）
   - 特に **import 方向 / レイヤ責務 / 命名規則** を全ファイルでチェック
   - 「使うライブラリ」リストと実依存（`pyproject.toml` / `package.json` / `go.mod`）の乖離

8. **CLAUDE.md / MEMORY.md との整合**
   - 「絶対ルール」「コーディング規約」「コメントの書き方」に違反していないか
   - 過去の feedback memory（`~/.claude/projects/<slug>/memory/`）と矛盾していないか

#### 出力位置

このステップで見つけた指摘は **コミット別レビューには混ぜず**、`## 要件定義整合チェック` という独立セクションで出力する：

```markdown
## 要件定義整合チェック

### 受け入れ条件の充足状況（authentication.md §受け入れ条件）

- [x] (1) `state` 不一致 → /login?auth_error=state_invalid 302 ✅ 実装 [auth.py:194](path#L194)
- [ ] (2) ログイン済みユーザーが /login を開くとホームへ ❌ Frontend 未実装（本 PR スコープ外なので OK）
- [x] (3) 同 GitHub アカウント再ログインで同一 user_id ✅ 実装 [auth.py:67-75](path#L67-L75)
- ...

### ADR との整合
- ADR 0047 §Cookie 仕様：実装と一致 ✅
- backend.md「認証: authlib」：実装が httpx 直叩きで乖離 ❌ → rules を更新すべき
- ...

### ステータス節の正確性
- authentication.md `## ステータス` が `- [x] バックエンド実装完了` だが、テスト 0 件で「完了」を主張できる粒度か要再考
```

### 7. 最終全体チェック（コミット越境で見える指摘）

ここまでで **個別コミット指摘 + 要件整合指摘** が揃った。最後に **PR 全体を 1 枚絵として** 見直し、コミット単位では見えない問題を洗う。

#### 観点

1. **コミット粒度と順序**
   - 同 PR 内で「前の commit を覆す」変更がないか（add → remove / rename / 設計変更）
   - 純メリット視点で **何 commit に圧縮できたか** を概算（「13 commits 中 5 件が後で覆されており、圧縮すれば 8 commits」）
   - コミットの並びが「依存層 → 利用層」になっているか（基盤層が後ろにあると bisect が辛い）

2. **テストカバレッジ**
   - 新規ファイル / 新規関数に対応するテストが本 PR に含まれるか
   - 既存テストが壊れていないか（CI 結果 / `mise run test` 実行ログ）
   - 「テストは別 PR」と書かれていても、本 PR にマージ前に必要なテストが何か明示する

3. **生成物 / artifact の整合**
   - `apps/api/openapi.json` / `apps/api/job-schemas/*.json` / `apps/web/src/__generated__/` 等の生成物が **手動編集されてないか / 最新の SSoT から再生成されているか**
   - 生成コマンド（`mise run types-gen` 等）を回した結果と差分が一致するか

4. **設定値 / 環境変数の漏れ**
   - 新規 Settings フィールドが `.env.example` に追加されているか
   - 本番 / staging / dev で値が分かれるべき設定に、安全装置（validator / required check）が入っているか

5. **DB マイグレーション**
   - 新規 migration が `down_revision` で正しく親に繋がっているか
   - 既存 head と分岐していないか（`alembic merge heads` が必要な状態）
   - autogenerate の限界（拡張 / index rename / data migration）を手動補完できているか

6. **セキュリティの最終一読**
   - 秘密情報のログ漏洩（sid / token / password / API key を `logger.info` に流していないか）
   - SQL injection / コマンド injection / オープンリダイレクト / SSRF / XXE の余地
   - 認証 / 認可ガードの抜け（特に「自分のリソースか」チェック）
   - Cookie 属性（HttpOnly / Secure / SameSite / Path / Domain）の一貫性

7. **observability / 運用**
   - 構造化ログ（OpenTelemetry trace_id）に新規経路が乗っているか
   - エラー時に再現可能な情報（request_id / 失敗箇所）がログに残るか
   - ヘルスチェック（/healthz / /readyz）が新規依存（Redis 等）を含むか

8. **後方互換 / 移行コスト**
   - 既存ユーザー / 既存セッション / 既存データに対するマイグレーションパスが必要か
   - 「Cookie 名変更で既存セッションが読めなくなる」のような破壊的変更が PR 内にあるか

9. **マージ後に何が壊れる可能性があるか**
   - ローカル動作 vs 本番動作の差（env var / Secure flag / domain 設定）
   - Feature flag や段階リリース機構が必要か

#### 出力位置

このステップの指摘は `## 全体横断の指摘` として出力する（既存セクション）。さらに以下のサブカテゴリで整理：

- 設計レベル
- コミット粒度
- テスト・CI
- 生成 artifact
- セキュリティ最終一読

### 8. 仕分け（純メリットのみ）

各指摘を二択で振り分ける：

- **対応すべき**：機能 / 安全性 / 保守性 / 整合性が **明確に上がる** もの
- **対応不要**：仕様準拠 / 規約準拠 / 設計判断として妥当 / 既知のトレードオフを受容済み のもの

「対応した方がいいかも」「nice to have」「将来検討」のような **曖昧カテゴリは作らない**。判断が割れる場合は「対応すべき」に倒し、理由欄で「ただし優先度低」と付記する。

### 9. レビュー本文の組み立て

以下の構造で出力する：

```markdown
# PR #<N> レビュー — <タイトル>

## 全体評価

<2〜4 文。PR の規模・スコープ・全体的な品質感 + 仕分け結果の総数（対応すべき X 件 / 対応不要 Y 件）>

## コミット別レビュー

### 【1】 [<sha>](<重要ファイルへのリンク>) <type(scope): subject>

**対応すべき**
- (1) 指摘内容…
- (2) 指摘内容…

**対応不要**
- (3) 指摘内容…

### 【2】 ... 以下全コミット

## セキュリティチェック

### Critical（マージ前必須）
- (番号) 一行サマリ

### High（マージ前推奨）
- (番号) 一行サマリ

### Medium / Low
- (番号) 一行サマリ

## 要件定義整合チェック

- 受け入れ条件の充足状況（1 項目ずつ）
- ビジネスルールの実装対応
- API 仕様（OpenAPI）と要件 JSON 例の一致
- ADR との整合
- .claude/rules/ 規約との整合
- ステータス節の正確性

## 全体横断の指摘

PR 単体では現れず、複数コミットを通して見える指摘をまとめる：
- 設計レベル
- コミット粒度
- テスト・CI
- 生成 artifact
- セキュリティ最終一読
- ドキュメント・規約 drift

## 総括

### 優先度高（マージ前に潰したい）
- (番号) [スコープ内/外] 一行サマリ (概算: ...)

### 優先度中（短期で対応）
- (番号) [スコープ内/外] 一行サマリ (概算: ...)

### スコープ外で要フォローアップ（別 PR / Issue 化推奨）
- (番号) 一行サマリ + フォロー先（別 PR タイトル案 / 既存 Issue 番号）

### 対応不要（設計判断として OK）
- 設計判断 / 規約準拠の要約
```

**スコープ内 / 外の振り分け原則**：

- 同じ「対応すべき」指摘でも、スコープ内なら本 PR で潰す、スコープ外なら別 PR / Issue でフォロー、と推奨アクションが変わる
- スコープ判定の根拠は **PR 概要 / コミットメッセージ / 関連要件 .md の宣言** に置く（レビュアーの主観ではなく文書化された宣言）
- スコープ外でも Critical（セキュリティ重大）は本 PR に取り込みを推奨する旨を明示

### 10. 出力の長さ方針

- **長さの上限を作らない**：気付いた指摘は全部書く（ユーザーが明示しなくても、このスキルが呼ばれた = 網羅性を求めている）
- 通し番号を振って後から会話で「(40) について詳しく」と参照しやすくする
- コード位置は **markdown リンク必須**（`[file.py:42](path/file.py#L42)`）。VSCode 上で 1 クリックで開ける

## やらないこと

- **工数を判断軸にしない**：工数推定の記載自体は可。ただし「半日かかるから対応不要」のように **工数を理由に仕分けない**。仕分けは純粋なメリット / デメリットのみ
- **対応の優先度を時間軸で表現しない**：「次スプリント」「R7 以降」等は除外（優先度は Critical / High / Medium / Low の重大度で表現）
- **スコープ外を「対応不要」と即断しない**：スコープ外でも純メリットで対応すべきものは「対応すべき [スコープ外]」として出す（PR で対応するか、フォロー PR / Issue を切るかは別判断）
- **「LGTM」だけで終わらせない**：対応すべき指摘がゼロでも「対応不要」の理由を列挙して網羅性を担保
- **生成 AI 文言を入れない**（CLAUDE.md「絶対ルール」）

## 関連

- レビュー対象 PR の作成は `/pr` 等のカスタムコマンド経由を推奨（本スキルは作成済み PR を対象とする）
- 自分の作業ブランチを push 前にセルフレビューする用途にも使える（`gh pr create --draft` 後に本スキルを回す）
