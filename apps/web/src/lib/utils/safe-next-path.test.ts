// safeNextPath の単体テスト。
//   要件: authentication.md §2.5 バリデーション + §2 受け入れ条件
//   - "/" で始まる相対パスのみ許容
//   - "//evil.com" / "http(s)://..." / "/\\evil" 系は弾く
//   - URL エンコード経由（"/%2F%2Fevil.com" 等）の "//" 復元も弾く
//   - 不正値・空はフォールバック（既定 "/"）に倒す
//
//   API 側の同一ルール実装は apps/api/app/routers/auth.py の `_safe_next_path`。
//   仕様変更時は両方の実装 + テストを更新する（SSoT は authentication.md §2.5）。
import { describe, expect, it } from "vitest";

import { safeNextPath } from "./safe-next-path";

describe("safeNextPath", () => {
  describe("正常系: 同一オリジン相対パスはそのまま返る", () => {
    it("ルート '/' を許容", () => {
      expect(safeNextPath("/")).toBe("/");
    });

    it("通常のパス '/problems' を許容", () => {
      expect(safeNextPath("/problems")).toBe("/problems");
    });

    it("クエリ・ハッシュ付きパスも保持する", () => {
      expect(safeNextPath("/problems?difficulty=easy#top")).toBe("/problems?difficulty=easy#top");
    });

    it("ネストパス '/problems/123' を許容", () => {
      expect(safeNextPath("/problems/123")).toBe("/problems/123");
    });
  });

  describe("異常系: 外部 URL / 不正な値はフォールバックに倒れる", () => {
    it("protocol-relative '//evil.com' を弾く", () => {
      expect(safeNextPath("//evil.com")).toBe("/");
    });

    it("'http://evil.com' を弾く", () => {
      expect(safeNextPath("http://evil.com")).toBe("/");
    });

    it("'https://evil.com' を弾く", () => {
      expect(safeNextPath("https://evil.com")).toBe("/");
    });

    it("バックスラッシュ経由 '/\\\\evil.com' を弾く（一部ブラウザで // 相当扱い）", () => {
      expect(safeNextPath("/\\evil.com")).toBe("/");
    });

    it("'/' で始まらない相対パス 'problems' を弾く", () => {
      expect(safeNextPath("problems")).toBe("/");
    });

    it("空文字を弾く", () => {
      expect(safeNextPath("")).toBe("/");
    });

    it("null を弾く", () => {
      expect(safeNextPath(null)).toBe("/");
    });

    it("undefined を弾く", () => {
      expect(safeNextPath(undefined)).toBe("/");
    });
  });

  describe("異常系: URL エンコード経由の // を弾く（中段チェック）", () => {
    it("'/%2F%2Fevil.com'（デコードで //evil.com になる）を弾く", () => {
      expect(safeNextPath("/%2F%2Fevil.com")).toBe("/");
    });

    it("'/%2Fevil.com'（デコードで //evil.com になる）を弾く", () => {
      // /%2Fevil.com → /\evil.com 相当ではなく "/" + "/evil.com" = "//evil.com"
      expect(safeNextPath("/%2Fevil.com")).toBe("/");
    });

    it("不正な URL エンコード（decodeURIComponent が URIError を投げる）を弾く", () => {
      // 末尾 % は不正なエスケープ列。decodeURIComponent が URIError を投げる。
      expect(safeNextPath("/%E0%A4%A")).toBe("/");
    });
  });

  describe("フォールバック引数のカスタム指定", () => {
    it("第 2 引数でフォールバック先を上書きできる", () => {
      expect(safeNextPath("https://evil.com", "/login")).toBe("/login");
    });

    it("空入力でも第 2 引数のフォールバックが使われる", () => {
      expect(safeNextPath(null, "/dashboard")).toBe("/dashboard");
    });
  });
});
