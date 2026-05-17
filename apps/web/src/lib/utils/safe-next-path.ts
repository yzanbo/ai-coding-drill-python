// safeNextPath: ?next= で渡された遷移先を「同一オリジンの相対パスのみ」に
//   絞り込む。攻撃者が `?next=https://evil.com` のような外部 URL を仕込んで
//   フィッシングサイトへ誘導するのを防ぐ（オープンリダイレクト対策）。
//
//   要件: authentication.md §2.5 バリデーション
//   - "/" で始まる相対パスのみ許容
//   - "//evil.com" や "http://..." 等は除外
//   - "/%2F%2Fevil.com" 等の URL エンコード経由で "//" に解凍される値も弾く
//   - 不正値はフォールバック先（既定: "/"）を返す
//
//   API 側にも同じ業務ルールの実装あり: apps/api/app/routers/auth.py の
//   `_safe_next_path`。片方を変えたら必ずもう片方も更新する（business rule の
//   重複実装は authentication.md §2.5 を SSoT としている）。
const FALLBACK = "/";

export function safeNextPath(
  value: string | null | undefined,
  fallback: string = FALLBACK,
): string {
  if (!value) return fallback;
  // 前段チェック（生の値）: "/" 始まりかつ "//" や "/\\" でないこと。
  if (!value.startsWith("/") || value.startsWith("//") || value.startsWith("/\\")) {
    return fallback;
  }
  // 中段チェック（デコード後の値）: "/%2F%2Fevil.com" 等のエンコード経由で
  //   "//evil.com" に解凍される攻撃を弾く。不正なエスケープ列が来た時は
  //   decodeURIComponent が URIError を投げるので try/catch で受け止める。
  try {
    const decoded = decodeURIComponent(value);
    if (decoded.startsWith("//") || decoded.startsWith("/\\")) {
      return fallback;
    }
  } catch {
    return fallback;
  }
  // 後段チェック: ブラウザの URL パーサで「相対パスとして解釈した時、
  //   同一オリジン内に留まるか」を確認する。dummy オリジンで組み立てて検証する。
  try {
    const base = "http://example.com";
    const url = new URL(value, base);
    if (url.origin !== base) return fallback;
    return url.pathname + url.search + url.hash;
  } catch {
    return fallback;
  }
}
