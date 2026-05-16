// Vitest 初期化ファイル（vitest.config.ts の setupFiles から読まれる）。
// @testing-library/jest-dom: toBeInTheDocument / toHaveTextContent などの
//   DOM 用 matcher を expect に組み込み、テストの記述を読みやすくする。
import "@testing-library/jest-dom/vitest";
