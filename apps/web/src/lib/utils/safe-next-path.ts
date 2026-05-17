// safeNextPath: ?next= で渡された遷移先を「同一オリジンの相対パスのみ」に
//   絞り込む。攻撃者が `?next=https://evil.com` のような外部 URL を仕込んで
//   フィッシングサイトへ誘導するのを防ぐ（オープンリダイレクト対策）。
//
//   要件: authentication.md §2.5 バリデーション
//   - "/" で始まる相対パスのみ許容
//   - "//evil.com" や "http://..." 等は除外
//   - 不正値はフォールバック先（既定: "/"）を返す
//
//   ホスト判定は new URL に base を渡し、組み立て後の origin が base と
//   一致するかで確認する（"%2F%2Fevil.com" 等のエンコード回避にも頑健）。
const FALLBACK = "/";

export function safeNextPath(
  value: string | null | undefined,
  fallback: string = FALLBACK,
): string {
  if (!value) return fallback;
  // 単純な前段チェック: "/" 始まりかつ "//" や "/\\" でないこと。
  if (!value.startsWith("/") || value.startsWith("//") || value.startsWith("/\\")) {
    return fallback;
  }
  // ブラウザの URL パーサで「相対パスとして解釈した時、同一オリジン内に
  //   留まるか」を確認する。dummy オリジンで組み立てて検証する。
  try {
    const base = "http://example.com";
    const url = new URL(value, base);
    if (url.origin !== base) return fallback;
    return url.pathname + url.search + url.hash;
  } catch {
    return fallback;
  }
}
