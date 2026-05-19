# 0048. ユーザー向けテーブルにソフトデリートを採用（`deleted_at` カラム方式）

- **Status**: Accepted
- **Date**: 2026-05-19
- **Decision-makers**: yzanbo

## Context（背景・課題）

[01-data-model.md](../requirements/3-cross-cutting/01-data-model.md) の初期方針は「ソフトデリートは原則使わない / `deleted_at` 列を追加しない」だった。理由は「行の管理を単純に保つ」「クエリで `deleted_at IS NULL` フィルタを毎回書く負担を避ける」。

しかし、本プロジェクト（学習サイト）の運用要件を改めて整理した結果、ハードデリート前提では成立しない要件が複数あることが明確になった：

- **ユーザー退会**：`users` を物理削除すると、`submissions.user_id` の参照整合性が壊れる。FK を `ON DELETE CASCADE` にすると過去の解答履歴が消え、`problems` ごとの正答率・難易度推定統計まで崩れる。`SET NULL` にしても「誰が解いたか不明」な行が残り、学習履歴画面の所有権チェック（[learning.md](../requirements/4-features/learning.md)）が成立しない
- **問題の取り下げ**：問題に誤りが見つかった / カテゴリ運用方針が変わった等で公開停止したいが、過去に解答した `submissions` 行は履歴画面で参照可能であり続ける必要がある
- **解答履歴の削除要望**：ユーザーが「黒歴史の解答を消したい」と要望した場合、本人画面からは消したいが、`problems` 別の難易度推定・全体統計には残したい場面がある（本人視点 ≠ 集計視点）

これらは MVP 段階から発生しうるため、初期方針を反転して `deleted_at` を導入する。

## Decision（決定内容）

履歴・参照整合性が重要な **ユーザー向けテーブル 3 つ**（`users` / `problems` / `submissions`）に `deleted_at TIMESTAMPTZ NULL` を追加し、ソフトデリートを採用する。それ以外（`auth_providers` / `generation_requests` / `jobs`）は引き続きハードデリート（または TTL バッチ物理削除）。

運用詳細の SSoT は [01-data-model.md: 削除方針](../requirements/3-cross-cutting/01-data-model.md#削除方針ソフトデリート採用) に置き、本 ADR は採用根拠と代替案を扱う。

要点：

- `deleted_at IS NULL` フィルタは**全クエリで明示的に書く**（暗黙フィルタを置かない）。本人画面と集計クエリでフィルタ条件を切り替えられる利点を活かす
- `users` の退会では `deleted_at` セットと同時に PII（`email` / `display_name`）を NULL クリアする匿名化を併用
- 古いソフトデリート行は TTL バッチで物理 DELETE して容量を抑える
- ソフトデリート対象テーブルの履歴系インデックスは `WHERE deleted_at IS NULL` の部分インデックスで実装

## Why（採用理由）

### 参照整合性を構造的に守れる

物理削除では FK 参照先が消えるため `submissions` や `auth_providers` の存在を前提とした統計・履歴画面が壊れる。`deleted_at` セットなら親行は残るので、FK 参照は安全に維持される。

### 「本人視点」と「集計視点」を 1 つのテーブルで両立できる

- 本人画面：`WHERE deleted_at IS NULL` で生きている行のみ表示
- 全体統計・難易度推定：`deleted_at` を無視して全行を集計

物理削除では集計の前提が不可逆に壊れるが、ソフトデリートなら呼び出し側のクエリでスイッチできる。

### 誤削除からの復旧が可能

`UPDATE ... SET deleted_at = NULL` で復活させられる。MVP 段階の運用ミス（管理画面で誤って問題を削除した等）への保険になる。

### PII 匿名化と分離して書ける

退会時の PII クリア（GDPR 的要件）と「論理削除マーカー」を別カラムに分けることで、「ユーザーは退会したが過去解答は統計に残す」「PII は消すが匿名 ID として参照を残す」といったポリシーを表現できる。

### 明示的なフィルタを規約として課す

SQLAlchemy の global event listener 等で暗黙フィルタを仕掛けると、Worker / 集計クエリで「削除済も読みたい」場面に逐一例外処理が要る。**毎回 `deleted_at IS NULL` を書く**ルールに統一することで、読み手にとってクエリの挙動が明示的になる。

## Alternatives Considered（検討した代替案）

| 候補 | 概要 | 採用しなかった理由 |
|---|---|---|
| **ハードデリート継続**（旧方針） | 物理 DELETE のみ。FK は CASCADE / SET NULL で対処 | 学習履歴・正答率統計が崩れる。退会・問題取り下げの現実的な要件に応えられない |
| **`status` カラムで論理削除を表現**（`status='archived'` 等） | 既存の状態カラム規約に乗せる | `status` は本来「ライフサイクル状態」を表すべきで、「削除されたか」とは直交する。両者を混ぜると state machine が肥大化する。**`problems` の `published` / `archived` は別途 `status` で扱う**が、それは「削除」ではなく「公開状態」 |
| **アーカイブ用の別テーブル**（`deleted_users` / `deleted_problems` 等） | 削除時に別テーブルへ移動 | テーブル数が倍増し、FK 設計が複雑化する。`submissions` から見た親の参照先が「いる場所」によって変わるため、JOIN ロジックが破綻する |
| **イベントソーシング** | 削除を Event として記録、現在状態を投影で再構築 | プロジェクト規模に対して過剰。学習コスト・実装コストが見合わない |
| **全テーブルにソフトデリート**（auth_providers / generation_requests / jobs にも） | 一貫性のために全てに `deleted_at` を付ける | これらは履歴保存の意味が薄く、TTL バッチ物理削除のほうが容量効率が良い。一貫性のために不要なオーバーヘッドを払う必要はない |

## Consequences（結果・トレードオフ）

### 得られるもの

- ユーザー退会・問題取り下げ・解答削除の要件が、参照整合性を壊さずに実装できる
- 集計クエリと本人画面でフィルタを切り替えられる
- 誤削除からの復旧経路を確保
- PII 匿名化と論理削除を独立して扱える

### 失うもの・受容するリスク

- **全クエリで `deleted_at IS NULL` を書く規律が必要**：書き忘れると削除済データが画面に出る。コードレビュー / pytest の test fixture で削除済行を混ぜて検証する等で担保する
- **テーブル容量が増える**：削除しても物理的には残る。TTL バッチ（例：90 日経過行を物理 DELETE）で対処
- **`UNIQUE` 制約の扱いに注意**：`users.email` を unique にする場合、「退会した user.email を別ユーザーが再利用できるか」を決める必要がある。`deleted_at` を unique 制約に含めるか、PII クリア時に email を NULL にすることで衝突を回避する（MVP では PII NULL クリア方式を採用）
- **インデックスサイズ**：履歴クエリの複合インデックスを部分インデックス（`WHERE deleted_at IS NULL`）にして抑える

### 将来の見直しトリガー

- ソフトデリート行が全体の 50% を超える等、容量・性能影響が観測されたら TTL 短縮 or 別テーブル退避を再検討
- `deleted_at IS NULL` フィルタの書き忘れによる事故が複数回発生したら、ORM レベルの暗黙フィルタ + 明示的「全件参照」API（archived include 等）への切替を検討

## References

- [01-data-model.md: 削除方針](../requirements/3-cross-cutting/01-data-model.md#削除方針ソフトデリート採用) — 運用詳細の SSoT
- [ADR 0037: SQLAlchemy 2.0 + Alembic 採用](./0037-sqlalchemy-alembic-for-database.md) — 個別カラム定義はモデルが SSoT
- [grading.md](../requirements/4-features/grading.md) / [learning.md](../requirements/4-features/learning.md) — `submissions` を参照する画面・統計の要件
