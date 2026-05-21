# 役割:
#   apps/api/job-schemas/<job-name>.schema.json を 1 件ずつ quicktype に渡して
#   Worker（Go）側の Go 構造体を生成する。
#
# 背景:
#   quicktype に --src DIRECTORY を渡すと、--src-lang schema を付けても各ファイルを
#   JSON Schema ではなく JSON データとして読んでしまい、スキーマ自身の構造（properties
#   / required / title 等のフィールドを持つ struct）を生成してしまう（ADR 0006、R0-11
#   検証時に判明）。--src を使わずファイルを positional 引数で 1 個ずつ渡すと
#   --src-lang schema が正しく効くため、本スクリプトでループする。
#
# 出力:
#   <worker_dir>/internal/jobtypes/<job-name>.go
#   各ファイルに 1 つの Pydantic JobPayload に対応する Go struct + Unmarshal/Marshal 関数。
#   ファイル名は schema 名（kebab-case）と一致、struct 名は schema の "title" を採用。
#
# 命名規約:
#   schema title が Pydantic クラス名（例: HealthCheckJobPayload）なので、
#   quicktype --top-level "<title>" でクラス名と完全一致した struct 名を得る。
#
# 実行方法:
#   uv run python -m scripts.generate_worker_jobtypes <worker_dir>
#   （mise タスク: worker:<worker>:types-gen から呼ばれる）

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: generate_worker_jobtypes.py <worker_dir>", file=sys.stderr)
        return 2

    worker_dir = Path(argv[1]).resolve()
    api_root = Path(__file__).resolve().parent.parent
    schemas_dir = api_root / "job-schemas"
    out_dir = worker_dir / "internal" / "jobtypes"

    if not out_dir.is_dir():
        print(f"error: {out_dir} does not exist", file=sys.stderr)
        return 1

    # quicktype は PATH 上に居る前提（mise.toml [tools] に npm:quicktype を登録済）。
    quicktype = shutil.which("quicktype")
    if quicktype is None:
        print("error: quicktype not found on PATH (mise install して下さい)", file=sys.stderr)
        return 1

    # 既存生成物を全て掃除して再生成（schema を削除した時の取り残し防止）。
    # .gitignore と README.md は残す（jobtypes/.gitignore で commit 対象指定済み）。
    for old in out_dir.glob("*.go"):
        old.unlink()

    schemas = sorted(schemas_dir.glob("*.schema.json"))
    if not schemas:
        print(
            "no *.schema.json under apps/api/job-schemas/（"
            "apps/api/app/schemas/jobs/ に *JobPayload を追加後、"
            "mise run api:job-schemas-export を実行して下さい）"
        )
        return 0

    wrote = 0
    for schema_path in schemas:
        base = schema_path.name.removesuffix(".schema.json")
        try:
            schema_doc = json.loads(schema_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            print(f"error: {schema_path} is not valid JSON: {e}", file=sys.stderr)
            return 1

        # title が無いスキーマは Pydantic 経由ではないので除外（ADR 0006 の運用前提）。
        title = schema_doc.get("title")
        if not isinstance(title, str) or not title:
            print(
                f"error: {schema_path.name} has no string 'title' field "
                "（Pydantic 由来の schema は自動で title が入る）",
                file=sys.stderr,
            )
            return 1

        out_file = out_dir / f"{base}.go"
        cmd = [
            quicktype,
            "--lang", "go",
            "--src-lang", "schema",
            "--package", "jobtypes",
            "--top-level", title,
            "--out", str(out_file),
            str(schema_path),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(
                f"error: quicktype failed for {schema_path.name}\n"
                f"  cmd: {' '.join(cmd)}\n"
                f"  stdout: {result.stdout}\n"
                f"  stderr: {result.stderr}",
                file=sys.stderr,
            )
            return 1

        print(f"wrote {out_file.relative_to(worker_dir.parent.parent.parent)} (top-level={title})")
        wrote += 1

    # 共有 $defs 型の重複を解消する。
    #   Pydantic は TraceContext を共通サブモデルとして使うため、
    #   schema 側で $ref で参照される。quicktype は 1 schema = 1 file で
    #   個別生成するので、複数の schema が同じ $def を参照すると
    #   同名の Go type 宣言が複数ファイルに出て redeclared エラーになる。
    #   全ファイルは同じ package（jobtypes）なので、最初の 1 ファイルに残し
    #   他のファイルからは同名の型 / コメント / Unmarshal/Marshal を削る。
    _dedupe_shared_types(out_dir)

    print(f"summary: wrote {wrote}, total {len(schemas)}")
    return 0


# _TYPE_BLOCK_RE: `type Name struct {...}` を 1 ブロック単位でマッチする正規表現。
#   名前は ASCII の大文字始まり PascalCase 前提（quicktype の出力規約）。
#   非貪欲 + 改行マッチで {...} 内に他の type が無いことを利用する。
_TYPE_BLOCK_RE = re.compile(
    r"^// [^\n]*\n(?:// [^\n]*\n)*type ([A-Z][A-Za-z0-9_]*) struct \{[^{}]*\}\n",
    re.MULTILINE,
)


def _dedupe_shared_types(out_dir: Path) -> None:
    """複数 .go ファイルに同名で出てくる type 宣言ブロックを最初の 1 個に絞る。

    削除対象は「同名の type ブロックが 2 個以上ある」ものだけ。
    各 schema 固有の Payload 型（GradingJobPayload 等）は名前が違うので残る。
    """
    go_files = sorted(out_dir.glob("*.go"))
    if not go_files:
        return

    # 1 周目: 全ファイルから type ブロックを抜き出し、出現ファイルを記録する。
    occurrences: dict[str, list[Path]] = {}
    for go_file in go_files:
        text = go_file.read_text(encoding="utf-8")
        for match in _TYPE_BLOCK_RE.finditer(text):
            type_name = match.group(1)
            occurrences.setdefault(type_name, []).append(go_file)

    # 重複しているものだけ抽出（1 ファイルしか無い型は触らない）。
    duplicated = {name: paths for name, paths in occurrences.items() if len(paths) > 1}
    if not duplicated:
        return

    # 2 周目: 各重複型について、最初に出てきたファイル以外から該当ブロックを削除する。
    #   alphabetical sort なので「最初」はファイル名昇順。
    for type_name, paths in duplicated.items():
        keeper = paths[0]
        for path in paths[1:]:
            text = path.read_text(encoding="utf-8")
            # 該当 type 名のブロックだけを削る正規表現。先頭コメント込み。
            pattern = re.compile(
                rf"^// [^\n]*\n(?:// [^\n]*\n)*type {re.escape(type_name)} struct \{{[^{{}}]*\}}\n",
                re.MULTILINE,
            )
            new_text, count = pattern.subn("", text)
            if count > 0:
                path.write_text(new_text, encoding="utf-8")
        other_count = len(paths) - 1
        print(
            f"dedup: kept {type_name} in {keeper.name}, "
            f"removed from {other_count} other file(s)"
        )


if __name__ == "__main__":
    sys.exit(main(sys.argv))
