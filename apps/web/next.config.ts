import type { NextConfig } from "next";

// API_PROXY_TARGET: Next.js 開発サーバから FastAPI へ転送する先。
//   ローカルでは :8000、デプロイ時は環境変数で上書きする。
//   ブラウザから見て同一オリジンで API を叩ける状態にすると、Cookie / CSRF が
//   クロスオリジン制約に引っかからないため、CORS 設定を入れずに済む。
const API_PROXY_TARGET = process.env.API_PROXY_TARGET ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  // rewrites: パスを別サーバへ「裏で」転送する仕組み（ブラウザの URL は変えない）。
  //   /auth, /health, /healthz は FastAPI 側のエンドポイント。Frontend からは
  //   相対パスで叩けるようにし、Set-Cookie や認証 Cookie を同一オリジンとして扱う。
  async rewrites() {
    return [
      { source: "/auth/:path*", destination: `${API_PROXY_TARGET}/auth/:path*` },
      { source: "/health", destination: `${API_PROXY_TARGET}/health` },
      { source: "/healthz", destination: `${API_PROXY_TARGET}/healthz` },
    ];
  },
  // headers: 全レスポンスに横断で被せるセキュリティヘッダー。
  //   Referrer-Policy: 外部サイト（GitHub の認可画面等）へ遷移する時に
  //     ?next= 等の内部 URL がそのまま Referer ヘッダーで漏れるのを防ぐ。
  //     "strict-origin-when-cross-origin" は「外部にはオリジンだけ送る」設定で、
  //     パスやクエリは外部に渡らない（同一オリジン遷移ではフル URL を保持）。
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [{ key: "Referrer-Policy", value: "strict-origin-when-cross-origin" }],
      },
    ];
  },
};

export default nextConfig;
