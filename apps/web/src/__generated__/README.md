# __generated__/

## __generated__/ とは何か

**人手で編集しない** 自動生成物の集積場所です。フォルダ名を二重アンダースコアで囲んで
「ここは生成物だぞ」と一目で分かるようにしています（[biome.jsonc](../../biome.jsonc) や
[knip.config.ts](../../knip.config.ts) もこの 1 つのパスを除外する設定になっている）。

| サブフォルダ | これは何か（役目） |
|---|---|
| `api/` | **Hey API** が `apps/api/openapi.json`（FastAPI が自動で書き出す OpenAPI 3.1）から生成した TS 型・Zod スキーマ・HTTP クライアント。FastAPI の Pydantic を正本（SSoT）として TS 側に展開する経路（[ADR 0006](../../../../docs/adr/0006-json-schema-as-single-source-of-truth.md)） |

## 再生成

API の Pydantic スキーマや router シグネチャが変わったら、下のコマンドで一括再生成します：

```bash
# 1. API 側で OpenAPI 3.1 JSON を書き出す
mise run api:openapi-export   # → apps/api/openapi.json

# 2. Web 側で Hey API を回して TS / Zod / HTTP クライアントを生成
mise run web:types-gen        # → apps/web/src/__generated__/api/

# 3. （両方を一気にやるなら）
mise run types-gen
```

CI は `mise run types-gen` を必須ステップに組み込み、生成物に差分が出たら **fail させる**
（生成物のコミット忘れ防止、[ADR 0006](../../../../docs/adr/0006-json-schema-as-single-source-of-truth.md)）。

## やってはいけないこと

- ❌ 中身を手で編集する（次の `mise run web:types-gen` で消える）
- ❌ ここから `src/` 配下を import する（終端なので、何も呼び返さない）
- ❌ 別の場所に生成物を置く（lint / knip / biome の除外設定が効かなくなる）

## 役目

- OpenAPI / JSON Schema から作った型・クライアントだけを置く
- 手書きの API ラッパ（エラー解釈・トークン処理等）は `src/lib/api/` 側で書く
