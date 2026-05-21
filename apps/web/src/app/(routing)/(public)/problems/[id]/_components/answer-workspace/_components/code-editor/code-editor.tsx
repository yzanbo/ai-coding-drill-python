"use client";

// CodeEditor: CodeMirror 6 ベースの TypeScript コードエディタ（R1-4）。
//   - 構文ハイライト（@codemirror/lang-javascript の jsx + typescript モード）
//   - basicSetup（行番号 / undo / 検索 / インデント等の標準セット）
//   - 編集内容を onChange で親に伝える（親が localStorage 保存）
//
//   ADR 0015 で CodeMirror 6 採用。ブラウザ内型診断（@typescript/vfs）は
//   段階導入：本コミットでは構文ハイライト + 基本操作のみで、型診断は
//   後続コミットで追加する（要件 problem-display-and-answer.md §受け入れ条件
//   「エディタにインライン型診断・補完が出る」は未充足のまま残す）。

import { javascript } from "@codemirror/lang-javascript";
import { EditorState, type Extension } from "@codemirror/state";
import { EditorView } from "@codemirror/view";
import { basicSetup } from "codemirror";
import { useEffect, useRef } from "react";

type CodeEditorProps = {
  value: string;
  onChange: (next: string) => void;
};

// 共通の Extension 定義。
//   javascript({ typescript: true, jsx: false }): .ts として扱う（jsx 構文不要）
//   EditorView.theme:
//     - 高さは指定せず、CodeMirror のデフォルト挙動（doc 行数に追従）に任せる。
//       行が増えれば自然に伸び、左の行番号 gutter も実際の行数分だけ表示される。
//     - fontSize / font-family のみ、サイト全体のデザイントークンに揃える。
//   EditorView.updateListener: テキスト変更を React state にブリッジ
const buildExtensions = (onChange: (next: string) => void): Extension[] => [
  basicSetup,
  javascript({ typescript: true, jsx: false }),
  EditorView.theme({
    "&": { fontSize: "0.875rem" },
    ".cm-scroller": {
      fontFamily: "var(--font-mono, ui-monospace, monospace)",
    },
  }),
  EditorView.updateListener.of((update) => {
    if (update.docChanged) {
      onChange(update.state.doc.toString());
    }
  }),
];

export const CodeEditor = ({ value, onChange }: CodeEditorProps) => {
  // CodeMirror の EditorView は React の管理外で生きるため、ref + useEffect で
  //   インスタンスをマウント / アンマウントする。
  const hostRef = useRef<HTMLDivElement | null>(null);
  const viewRef = useRef<EditorView | null>(null);
  // onChangeRef: setState 関数は親の再 render で identity が変わる可能性があり、
  //   EditorView を都度作り直すと履歴・カーソルが飛ぶ。ref に閉じ込めて最新版を
  //   updateListener から参照する形にすれば、view は 1 度だけ作って使い回せる。
  const onChangeRef = useRef(onChange);
  useEffect(() => {
    onChangeRef.current = onChange;
  }, [onChange]);

  // 初回マウントで EditorView を作成、アンマウントで destroy。
  //   value 初期値はマウント時の 1 回だけ初期 doc に反映する（以降の外部からの
  //   value 変更は下の useEffect で view.dispatch で差し替える）。
  // biome-ignore lint/correctness/useExhaustiveDependencies: 初回マウント時のみ EditorView を作る（value/onChange を deps に入れると view が作り直されてカーソル位置が飛ぶ）
  useEffect(() => {
    if (!hostRef.current) return;
    const view = new EditorView({
      state: EditorState.create({
        doc: value,
        extensions: buildExtensions((next) => onChangeRef.current(next)),
      }),
      parent: hostRef.current,
    });
    viewRef.current = view;
    return () => {
      view.destroy();
      viewRef.current = null;
    };
  }, []);

  // 親から渡される value が外部要因で変わった時（localStorage 復元、問題遷移等）に
  //   エディタの doc を差し替える。エディタの現在内容と同じなら no-op で
  //   無限ループ・カーソルジャンプを防ぐ。
  useEffect(() => {
    const view = viewRef.current;
    if (!view) return;
    const current = view.state.doc.toString();
    if (current === value) return;
    view.dispatch({
      changes: { from: 0, to: current.length, insert: value },
    });
  }, [value]);

  return (
    <section
      ref={hostRef}
      // aria-label: CodeMirror 内部の contenteditable が実際の入力面で、本要素は
      //   それを包む landmark。section + aria-label でスクリーンリーダーから
      //   「解答コードエディタ」エリアとして読まれる。
      // 高さは指定しない：CodeMirror の自然な高さ（doc 行数分）に任せる。
      //   行が増えれば section ごと縦に伸び、行番号 gutter は実際の行数分が見える。
      aria-label="解答コードエディタ"
      className="rounded-lg border border-border bg-card overflow-hidden focus-within:ring-2 focus-within:ring-ring"
    />
  );
};
