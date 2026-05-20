// /problems/new: 問題生成リクエスト画面。
//   - カテゴリ + 難易度を選んで送信
//   - 送信後は /problems/generate/:requestId に遷移（同期で待たせない設計）
//   要件: docs/requirements/4-features/problem-generation.md §問題生成画面
//
//   このページは認証必須。(authed) layout が未認証時の /login リダイレクトを担保する。
//   Client Component（フォーム入力 / 遷移）は子の ProblemGenerateForm 側に閉じ込め、
//   ページ本体は静的 RSC として見出し + 説明 + フォーム差し込みのみを担当する。

import { ProblemGenerateForm } from "./_components/problem-generate-form/problem-generate-form";

export default function NewProblemPage() {
  return (
    <main className="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-8 px-4 py-12">
      <header className="flex flex-col gap-2">
        <h1 className="text-2xl font-semibold">新しい問題を生成する</h1>
        <p className="text-sm text-muted-foreground">
          カテゴリと難易度を選ぶと、AI が新しい TypeScript
          問題を生成します。生成には少し時間がかかります（数秒〜数十秒）。
        </p>
      </header>
      <ProblemGenerateForm />
    </main>
  );
}
