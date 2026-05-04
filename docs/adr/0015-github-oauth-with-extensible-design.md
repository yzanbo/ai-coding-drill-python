# 0015. 認証は GitHub OAuth のみ実装、ただし複数プロバイダへ拡張可能な設計とする

- **Status**: Accepted
- **Date**: 2026-04-25
- **Decision-makers**: 神保 陽平

## Context（背景・課題）

ユーザー認証の方式と、将来の拡張性のバランスをどう取るか。

- ターゲットユーザー：プログラミング中級者（GitHub アカウントを持つ層が大多数）
- MVP の完成リスクを抑えたい
- 一方で、将来 Google / Email-Password 等を追加できないハードコード設計は避けたい
- 「実装は最小、拡張は容易に」という設計原則を反映したい

## Decision（決定内容）

**MVP では GitHub OAuth のみを実装**し、**複数プロバイダへの拡張容易性を構造的に確保する**。

### 実装方針
- 認証は **GitHub OAuth のみ**
- セッション管理：Cookie ベース（HttpOnly + Secure + SameSite=Lax）、ストレージは Redis（Upstash）、TTL 7 日

### 拡張容易性のための 3 つの設計
1. **Passport の Strategy パターンに沿う**（NestJS 標準）
   - `GitHubStrategy` を 1 ファイルに分離、`AuthModule` に登録
   - 将来：`GoogleStrategy` / `CredentialsStrategy` を新規ファイルとして追加するだけ
2. **DB スキーマで `users` と `auth_providers` を分離**
   - `users` テーブルにプロバイダ ID を持たせない
   - `auth_providers (provider, provider_id, user_id)` で紐付け管理
   - 1 ユーザーが将来複数プロバイダで紐づけ可能（アカウント統合）
3. **AuthService をプロバイダ非依存に実装**
   - `validateOAuthUser({ provider, providerId, email, displayName })` のような関数で各 Strategy から共通呼び出し

### やらないこと（YAGNI）
- 使わない Strategy を Module に登録しない
- Google / Twitter / Apple 用のテーブルやコードを先取りで書かない
- アカウント統合機能・プロバイダ切り替え画面は MVP に含めない

## Why（採用理由）

1. **ターゲット層との一致（GitHub アカウント所有が前提）**
   - 中級プログラマ層は GitHub アカウントを持つ層が大多数
   - 複数プロバイダを最初から実装するのはターゲットに対して過剰
2. **MVP 完成リスクの最小化**
   - 認証は本質機能ではないため、実装最小（GitHub Strategy 1 つ）で本質機能（LLM 生成・採点）に投資集中
   - 複数プロバイダ実装は 1〜2 日/プロバイダのコストが MVP 完成を圧迫する
3. **拡張容易性を「構造」で確保（YAGNI とのバランス）**
   - 実装は最小だが DB スキーマ（`users` と `auth_providers` 分離）と Strategy パターンで拡張余地を構造的に残す
   - ハードコード（`users.github_id`）は将来の拡張時に DB マイグレーション規模が大きく、設計判断のアピールも弱い
   - 「先取り実装」と「先取り構造」を区別する判断
4. **NestJS の設計哲学との整合**
   - Passport の Strategy パターンは NestJS 標準で、DI・Module 構造と自然に統合
   - NextAuth を Next.js 側に寄せると認証ロジックが分散し、API 中心の設計と矛盾
5. **アカウント統合という将来要件への対応余地**
   - `auth_providers` テーブル分離により、1 ユーザー × 複数プロバイダの構造が最初から成立
   - 将来「同じユーザーで GitHub と Google を統合」要望が出た場合のマイグレーションコストが小さい
6. **設計原則「実装は最小、拡張は容易に」の体現**
   - ポートフォリオで「YAGNI を機械的に適用するのではなく、拡張点を見極めて構造に残す」という判断を語れる

## Alternatives Considered（検討した代替案）

| 候補 | 概要 | 採用しなかった理由 |
|---|---|---|
| GitHub OAuth のみ + 拡張容易な設計 | （採用） | — |
| GitHub OAuth のみ + ハードコード（`users.github_id`） | シンプル | 拡張時に DB マイグレーション・コード書き換えが大規模に発生、設計判断のアピールが弱い |
| GitHub + Google + Email-Password を MVP から | 多様性 | 実装・運用コスト増（プロバイダごとに 1〜2 日）、本質機能（LLM 生成・採点）への投資が削られる、ターゲット層には過剰 |
| NextAuth（Auth.js）を Next.js 側に寄せる | 標準的フロント認証 | API が NestJS 中心の設計と合わない、認証ロジックが分散、NestJS の設計力アピールが弱まる |
| メール + パスワードのみ | パスワード管理が必要 | パスワードリセット・ハッシュ管理など実装範囲が広い、ターゲット層には魅力が薄い |

## Consequences（結果・トレードオフ）

### 得られるもの
- MVP の実装コスト最小（GitHub Strategy 1 つだけ）
- DB 設計が拡張容易（`auth_providers` テーブルで複数プロバイダ対応）
- Passport の Strategy パターンに従うことで NestJS の DI 設計と整合
- 将来追加コストが低い（新規 Strategy ファイル + Module 登録 + ボタン追加で 1〜2 時間）
- 「実装は最小、拡張は容易に」という設計原則をポートフォリオで語れる
- 1 ユーザーが複数プロバイダで紐づく将来要件（アカウント統合）にも対応可能な構造

### 失うもの・受容するリスク
- `auth_providers` テーブル分離により JOIN が 1 つ増える（パフォーマンス影響は軽微）
- Email カラムに UNIQUE 制約を付けない（複数プロバイダで同じメールが登録される可能性を許容）
- アカウント統合機能（同一メールで GitHub と Google を紐づける）は別途実装が必要

### 将来の見直しトリガー
- ユーザーから「Google でログインしたい」要望が一定数出た場合 → Google Strategy 追加
- 法人利用要件が出た場合 → SAML / SSO の追加検討
- 「同じユーザーが GitHub と Google を統合したい」要望が出た場合 → アカウント統合機能の実装

## References

- [01-overview.md: F-01 ユーザー認証](../requirements/1-vision/01-overview.md)
- [01-data-model.md: users / auth_providers](../requirements/3-cross-cutting/01-data-model.md)
- [02-architecture.md: AuthModule](../requirements/2-foundation/02-architecture.md#backend-apinestjs)
