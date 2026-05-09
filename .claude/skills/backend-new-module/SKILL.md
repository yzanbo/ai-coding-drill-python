---
name: backend-new-module
description: NestJS モジュールを規約通りにスキャフォールドする
argument-hint: "[feature-name] (例: notifications, ratings)"
---

# バックエンドモジュールのスキャフォールド

引数 `$ARGUMENTS` を機能名（単数形・ケバブケース、例：`notification`）として解釈する。

## 手順

1. [.claude/rules/backend.md](../../rules/backend.md) を読み、コーディング規約を確認する
2. 以下のファイルを `apps/api/src/$ARGUMENTS/` に作成する

### 作成するファイル

```
apps/api/src/$ARGUMENTS/
├── $ARGUMENTS.module.ts
├── $ARGUMENTS.controller.ts
├── $ARGUMENTS.service.ts
└── dto/
    ├── create-$ARGUMENTS.dto.ts
    ├── update-$ARGUMENTS.dto.ts
    └── $ARGUMENTS-response.dto.ts
```

### 準拠するルール（[.claude/rules/backend.md](../../rules/backend.md) より）

#### モジュール

- DrizzleModule は `@Global()` なので imports 不要
- 他モジュールのサービスを使う場合のみ imports に追加
- providers と exports を適切に設定

```typescript
@Module({
  imports: [],
  controllers: [XxxController],
  providers: [XxxService],
  exports: [XxxService],
})
export class XxxModule {}
```

#### コントローラ

- `@ApiTags('Xxx')` で Swagger グループ分け
- 全エンドポイントに `@ApiOperation({ summary: '...' })` + `@ApiOkResponse({ type: DtoClass })`
- 認証必須が既定（グローバルガード）。公開エンドポイントは `@Public()`
- `@CurrentUser()` で認証済みユーザー情報取得
- パスパラメータ：UUID なら `ParseUUIDPipe`、整数なら `ParseIntPipe`
- ビジネスロジックはサービスに委譲

#### サービス

- `private readonly logger = new Logger(ClassName.name)`
- Drizzle：`this.drizzle.db.query.<table>` または `this.drizzle.db.insert/update/delete(<table>)`
- 認証済みエンドポイントでは「自分のリソースか」を必ずチェック
- エラーは NestJS 例外（`NotFoundException`, `BadRequestException`, `ForbiddenException` 等）、メッセージは日本語
- ハードデリート方針（必要に応じて検討）

#### DTO

- `@ApiProperty()` + `class-validator` デコレータ
- `UpdateDto` は `PartialType(CreateDto)`
- クエリパラメータには `@Type(() => Number)`
- 命名：`Create*Dto`, `Update*Dto`, `*ResponseDto`, `*ParamDto`, `*QueryDto`

3. `app.module.ts` の imports に追加する

```typescript
@Module({
  imports: [
    // ... 既存
    XxxModule,
  ],
})
export class AppModule {}
```

4. **DB スキーマが必要な場合**：
   - `apps/api/src/drizzle/schema/$ARGUMENTS.ts` にスキーマ定義
   - `apps/api/src/drizzle/schema/index.ts` で export
   - `pnpm db:generate` でマイグレーション生成
   - 詳細は [.claude/rules/drizzle.md](../../rules/drizzle.md)

5. **共有スキーマ（JSON Schema）が必要な場合**：
   - `packages/shared-types/schemas/$ARGUMENTS.schema.json` 追加
   - `pnpm shared-types:generate` で型再生成
   - 詳細は [ADR 0006](../../../docs/adr/0006-json-schema-as-single-source-of-truth.md)

6. 作成したファイルの一覧をユーザーに提示する

7. ユーザーがこの後 `/backend-implement $ARGUMENTS` で実装に進められる旨を伝える
