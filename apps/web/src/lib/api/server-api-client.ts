// このファイルの役割：
//   Server Component（RSC）から FastAPI を叩くための Hey API クライアント。
//
// なぜ別クライアントが要るか：
//   - lib/api/api-client.ts が configure する共有 client は baseUrl="" 固定。
//     これはブラウザ実行時に Next.js の rewrites（next.config.ts）に乗せて
//     同一オリジン扱いにするための既定だが、RSC は Node.js 側で fetch するため
//     rewrites を通らない。空 baseUrl では Node.js fetch が URL を解決できず
//     "Failed to parse URL" で落ちる。
//   - したがって RSC からは「絶対 URL の API_PROXY_TARGET を baseUrl にした
//     別 client」を使う必要がある（ADR 0042 が示唆する RSC + fetch 経路）。
//
// 使い方：
//   import { serverApiClient } from "@/lib/api/server-api-client";
//   import { listProblemsApiProblemsGet } from "@/__generated__/api/sdk.gen";
//
//   const { data } = await listProblemsApiProblemsGet({
//     client: serverApiClient,
//     query: { page: 1 },
//   });
//
// 認証：
//   本ファイルが扱うのは「ゲスト閲覧可」エンドポイントを想定する。
//   将来 RSC から認証必須エンドポイントを叩く場合は、next/headers の cookies()
//   からセッション Cookie を取り出して Header に詰める拡張が必要になる
//   （MVP では未実装、必要になった時点で追加する）。

import { createClient, createConfig } from "@/__generated__/api/client";

// API_PROXY_TARGET: Next.js dev サーバ → FastAPI への転送先と同じ env。
//   next.config.ts の rewrites と SSoT を揃え、ブラウザ経路と RSC 経路で
//   API 接続先がずれないようにする。
//   本番デプロイ時に同じ env で API URL を上書きする想定。
const API_PROXY_TARGET = process.env.API_PROXY_TARGET ?? "http://localhost:8000";

// serverApiClient: RSC 用の Hey API クライアント。
//   - baseUrl: 絶対 URL を明示（Node.js fetch 用）
//   - credentials: "omit"（ゲスト用途のため Cookie を一切送らない、
//     誤って認証エンドポイントを叩いた時の意図しないリーク防止）
export const serverApiClient = createClient(
  createConfig({
    baseUrl: API_PROXY_TARGET,
    credentials: "omit",
  }),
);
