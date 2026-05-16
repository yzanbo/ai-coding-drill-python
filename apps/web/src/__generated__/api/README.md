# __generated__/api/

## __generated__/api/ とは何か

**Hey API** が `apps/api/openapi.json` から生成した TS 型・Zod スキーマ・HTTP クライアントの
出力先。中身は人が触らず、コマンド一発で再生成します。

このフォルダは「FastAPI の Pydantic を正本（SSoT）として、TS 側に展開する経路」の終端です
（[ADR 0006](../../../../../docs/adr/0006-json-schema-as-single-source-of-truth.md)）。
別の経路（Job キュー境界）は Go の Worker 側に展開されます。

## 何が入るか（再生成後の予定）

- `client/` — Hey API の HTTP クライアント関数（`getProblems(...)` / `postSubmission(...)` 等）
- `types.gen.ts` — エンドポイントの request / response 型
- `zod.gen.ts` — レスポンス検証用 Zod スキーマ
- `index.ts` — Hey API が自動で書き出すバレル（**手書きの index.ts 禁止ルールの例外**。
  生成物のため、人手で改変しない前提）

> 上記ファイル名は Hey API のバージョン・設定で変わる可能性あり。最新は
> `openapi-ts.config.ts`（後日設置）の出力設定が正本。

## 再生成

API 側のスキーマや router シグネチャを変えたら：

```bash
# 1. FastAPI から OpenAPI 3.1 を書き出し
mise run api:openapi-export    # → apps/api/openapi.json

# 2. Hey API を回して TS を生成
mise run web:types-gen         # → apps/web/src/__generated__/api/

# 両方一気に：
mise run types-gen
```

## やってはいけないこと

- ❌ 中身を手で編集する（次の `mise run web:types-gen` で消える）
- ❌ ここから `src/` 配下を import する（生成器が解決できないし、終端を壊す）
- ❌ ここに手書きのラッパ・interceptor を置く（手書きは [lib/api/](../../lib/api/) へ）
