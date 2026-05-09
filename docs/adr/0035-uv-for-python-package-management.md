# 0035. Python のパッケージ管理・モノレポ管理に uv を採用

- **Status**: Accepted
- **Date**: 2026-05-09
- **Decision-makers**: 神保 陽平

## Context（背景・課題）

[ADR 0033](./0033-backend-language-pivot-to-python.md) でバックエンドを Python に pivot し、[ADR 0034](./0034-fastapi-for-backend.md) で FastAPI を採用した。次に必要な判断は **Python のパッケージ管理・仮想環境管理・モノレポ管理ツールの選定**である。

選定にあたっての制約・要請：

- **Python バージョン管理 / 仮想環境 / 依存解決 / lockfile** を統合した運用感（pip + virtualenv + pyenv + lockfile ツールの寄せ集めは避ける）
- **lockfile による再現性**：CI / 本番デプロイで全員が同じ依存ツリーを再現できること
- **モノレポ対応**：複数 Python パッケージ（バックエンド本体 + 共有ライブラリ等）を 1 リポジトリで管理できる workspace 機能
- **依存整合性**：複数パッケージ間でバージョンずれが起きないこと（TS 側の syncpack 相当）
- **CI 高速化**：依存インストールが CI 時間のボトルネックにならないこと
- **エコシステム継続性**：2026 年時点で活発にメンテされ、今後数年は乗り換え不要であること

判断のために参照した情報源：

- [Python Dependency Management in 2026 - Cuttlesoft](https://cuttlesoft.com/blog/2026/01/27/python-dependency-management-in-2026/)
- [Best Python Package Managers 2026 - Scopir](https://scopir.com/posts/best-python-package-managers-2026/)
- [UV vs Poetry - BSWEN 2026](https://docs.bswen.com/blog/2026-02-12-uv-vs-poetry/)

## Decision（決定内容）

Python のパッケージ管理・仮想環境管理・モノレポ管理に **`uv`** を採用する。

- **依存解決・インストール**：`uv add` / `uv sync`（lockfile は `uv.lock`）
- **Python バージョン管理**：`uv python install` / `.python-version` ファイル
- **仮想環境**：`uv venv`（自動 `.venv` 配置）
- **モノレポ管理**：`uv` の workspaces 機能（`pyproject.toml` の `[tool.uv.workspace]`）で複数パッケージを統合管理
- **依存整合性**：`uv.lock`（単一 lockfile）が workspace 全体の整合性を保証するため、syncpack 相当の追加ツールは不要
- **設定 SSoT**：`pyproject.toml`（[ADR 0022 設定ファイル形式優先順位](./0022-config-file-format-priority.md) の Tier 2 ecosystem 慣習に該当）
- **脆弱性スキャン**：[`pip-audit`](https://github.com/pypa/pip-audit)（PyPA 公式）を採用し、`uv.lock` を入力源として CI で実行する
  - 入力源：`uv.lock`（`uv export --format requirements-txt` 経由 or `pip-audit` の `pyproject.toml` 対応）
  - 照会先 DB：PyPI Advisory Database + OSV.dev（Google）
  - CI 統合：`ci-success` umbrella ジョブ（[ADR 0031](./0031-ci-success-umbrella-job.md)）の `needs` に追加し、新規脆弱性混入を PR で fail-closed
  - Dependabot（[ADR 0028](./0028-dependabot-auto-update-policy.md)）との二重ゲート：Dependabot は GitHub Advisory を主としたパッケージ更新 PR、`pip-audit` は OSV.dev も含めた幅広スキャン。両者は補完関係
- **未使用 / 未宣言 / transitive dependency 検出**：[`deptry`](https://github.com/osprey-oss/deptry) を採用し、依存衛生を CI で機械強制する
  - 入力源：`pyproject.toml`（PEP 621 標準準拠）+ Python ソースファイル（import 解析）
  - 検出項目：宣言済みだが未使用 / import されているが未宣言 / transitive を直接 import している依存
  - CI 統合：`mise run api-deps-check` 経由で `ci-success.needs` に追加
  - 速度：依存セット 100 個規模で 165ms（fawltydeps 比 20 倍以上）、成長時も CI 時間を圧迫しない
  - **TS の Knip（[ADR 0021](./0021-r0-tooling-discipline.md)）に対称な dependency hygiene ゲート**として位置付ける

ruff（[ADR 0020](./0020-python-code-quality.md)）と同社（Astral）製のため、Python ツーリングを Astral エコシステムで揃える。

## Why（採用理由）

### 1. 2026 年の事実上のデファクト

- 「**新規 Python プロジェクトでは uv 開始が標準、他を選ぶ理由がほぼない**」状態（Cuttlesoft 2026 / Scopir 2026）
- 大企業の本番採用が進行中
- pip / virtualenv / pyenv / lockfile ツールを 1 ツールに統合し、Python 依存管理の歴史的な散逸を解消

### 2. 圧倒的な速度（10〜100x）

- Rust 実装で pip の 10〜100 倍高速
- Sentry の実依存セットでの計測：Poetry 比で cold install 約 3 倍高速、lockfile 生成も約 3 倍高速
- CI の依存インストール時間が大幅に短縮され、フィードバックサイクルが改善

### 3. Astral エコシステム統合の一貫性

- `ruff`（[ADR 0020](./0020-python-code-quality.md)）と同社製、設計思想が揃う
- `pyproject.toml` を中心に Astral 製ツールが連携する将来性
- 将来 `ty`（Python 型チェッカー）が GA すれば、lint+format / 型 / pkg 管理の 3 点が Astral で揃う（[ADR 0020 の見直しトリガー](./0020-python-code-quality.md)）

### 4. workspace 機能でモノレポ対応 + 依存整合性が一体

- pnpm workspaces 相当の機能を `uv` 単体で提供
- 単一 `uv.lock` が workspace 全体の依存整合性を保証 → **syncpack 相当の追加ツールが不要**
- TS 側で `pnpm workspaces + syncpack` 2 点運用していたものが Python では uv 1 点で完結

### 5. 脆弱性スキャン（`pip-audit`）を CI 標準ゲートに組み込む

- **PyPA 公式ツール**で、PyPI Advisory Database + OSV.dev（Google）を照会先とする
- `uv.lock` を入力源にできるため、本 ADR で確立する uv ベースの依存管理と一体運用可能
- Dependabot（[ADR 0028](./0028-dependabot-auto-update-policy.md)）が「更新 PR」で対応する一方、`pip-audit` は「**現在の lockfile に既知 CVE が無いか**」を毎 PR で検証する。**Dependabot 待ち時間中の脆弱性混入を防ぐ**第二層
- TS の `pnpm audit` / Go の `govulncheck` と対称的なゲートを Python にも整備、3 言語で脆弱性スキャン水準を揃える

### 6. 依存衛生（`deptry`）で TS の Knip と対称な dep ゲートを揃える

- **未使用 dependency / 未宣言 dependency / transitive dependency を 1 ツールで検出**：Knip の dep 検査機能（→ [ADR 0021](./0021-r0-tooling-discipline.md)）に対応する Python 側の対称ツール
- **uv ネイティブ対応**：`pyproject.toml`（PEP 621）から直接読み、`uv.lock` 経由で transitive を解析。本 ADR の uv 採用と一体運用
- **高速性**：fawltydeps 比 20 倍以上（実依存 100 個規模で 165ms）。**成長時も CI 時間を圧迫しない**
- **代替（FawltyDeps / pip-extra-reqs / poetry-udeps）を退ける根拠**：deptry が機能網羅性・速度・uv 対応で全項目において同等以上。乗り換え理由が無い
- **vulture（未使用関数 / クラス検出）は不採用**：FastAPI / Pydantic / SQLAlchemy のメタプログラミング多用環境では誤検知率が高く、allowlist 維持コストが検出メリットを上回る。実害のある未使用 import / variable は ruff の F401 / F841 でカバー済み（[ADR 0020](./0020-python-code-quality.md)）

### 7. PEP 標準に準拠

- `pyproject.toml` （PEP 517/518/621）ベース
- 標準 build backend を採用しているため、ライブラリ publish も問題なく可能
- 将来 uv から離れる必要が生じても、pyproject.toml を別ツール（Poetry / Hatch 等）が読める移行余地

## Alternatives Considered（検討した代替案）

| 候補 | 概要 | 採用しなかった理由 |
|---|---|---|
| **uv（採用）** | Astral 製、Rust 実装、pip + virtualenv + pyenv + lockfile を統合 | — |
| Poetry | 成熟した依存管理ツール、月間 6600 万 DL | uv 比で 3 倍遅い、lockfile 生成も遅い、Astral 統合の一貫性を失う。ライブラリ publish の workflow は Poetry が滑らかだが、本プロジェクトはアプリケーションなので publish は不要 |
| Hatch | PyPA 推奨、multi-environment テストマトリクス向け | ecosystem が uv / Poetry より小さい、ニッチ用途寄り。speed / monorepo 機能で uv に劣る |
| PDM | PEP 582 準拠、`__pypackages__` 方式 | ecosystem が小さく、エディタ・IDE 対応が遅れがち。uv の現状勢いに対して採用根拠が弱い |
| pip + venv + pip-tools | 標準ツールの組み合わせ | lockfile 生成が遅い、Python バージョン管理は別途 pyenv が必要、workspace 機能なし。TS 側で `pnpm workspaces` を捨てた理由（散逸）と同じ問題が起きる |
| Poetry + asdf | パッケージ管理は Poetry、Python 版数は asdf | 2 ツール構成で散逸、uv 単体に劣る |

## Consequences（結果・トレードオフ）

### 得られるもの

- **Python ツーリングを Astral エコシステム（uv + ruff、将来 ty）で統合**した一貫性
- **CI 高速化**：依存インストールが pip 比で 10〜100x、Poetry 比で 3x 高速
- **モノレポ + 依存整合性が uv 単体で完結**：syncpack 相当の追加ツール不要、設定保守コスト最小
- **`pyproject.toml` 中心の運用**：他ツールへの移行余地を残せる
- **lockfile が単一 SSoT**：workspace 全体の依存ツリーが 1 ファイルに集約

### 失うもの・受容するリスク

- **Astral 1 社依存**：ruff / uv / ty すべて Astral 製になり、同社の方針転換リスクが集中する。ただし全て OSS / Apache 2.0 ライセンスのため、フォーク継続は可能
- **比較的若いツール**（2024 年初公開、2026 年に成熟）：歴史的実績で Poetry に劣る
- **ライブラリ publish workflow は Poetry の方が滑らか**：本プロジェクトはアプリケーションなので影響なし
- **Astral の課金モデル変更リスク**：現状 OSS 無料だが、将来有料機能追加時に競合検討要

### 将来の見直しトリガー

- **uv の活発な開発が停滞した場合**（極めて低確率）→ Poetry / Hatch への移行を検討
- **Astral が方針を大きく転換した場合**（例：コア機能の有料化）→ pyproject.toml 互換ツールへの移行を検討
- **ライブラリ公開（PyPI publish）が必要になった場合** → Poetry 併用 or uv の publish 機能の成熟度を再評価

## References

- [ADR 0020: Python のコード品質ツールに ruff + pyright を採用](./0020-python-code-quality.md)（同社 Astral 製の lint+format ツール）
- [ADR 0033: バックエンドを Python に pivot](./0033-backend-language-pivot-to-python.md)（本 ADR の前提となる言語選定）
- [ADR 0034: バックエンド API に FastAPI を採用](./0034-fastapi-for-backend.md)
- [ADR 0024: syncpack による package.json 整合性](./0024-syncpack-package-json-consistency.md)（Superseded by 0033、TS 側の依存整合性ツール、本 ADR で Python 側を uv lockfile に集約）
- [ADR 0022: 設定ファイル形式優先順位](./0022-config-file-format-priority.md)（pyproject.toml の Tier 2 ecosystem 慣習）
- [uv 公式](https://docs.astral.sh/uv/)
- [Astral 公式](https://astral.sh/)
- [Python Dependency Management in 2026 - Cuttlesoft](https://cuttlesoft.com/blog/2026/01/27/python-dependency-management-in-2026/)
- [pip-audit 公式](https://github.com/pypa/pip-audit)（脆弱性スキャン）
- [deptry 公式](https://github.com/osprey-oss/deptry)（依存衛生）
- [deptry vs FawltyDeps 速度比較](https://news.ycombinator.com/item?id=39724132)（deptry 採用根拠）
