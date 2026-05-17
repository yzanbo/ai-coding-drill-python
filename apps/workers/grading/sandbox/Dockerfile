# 採点サンドボックス用イメージ（R0-8 step 3 で配置した skeleton、ADR 0009）。
#
# 役割：受験者の解答コード（TS）を tsx + Vitest で実行するための使い捨てコンテナ。
# 実際の volume mount / Cmd / リソース制限（--memory 256m / --cpus 0.5 /
# --network none 等）は採点 Worker（R1-5 の自動採点フェーズ）側で指定する。
#
# Node.js 版数は ../../../../mise.toml の `node = "24"` と揃える（FE 側の Node と
# 同じメジャーで動くことを保証）。

# node:24-alpine = Node.js 24 系の最新パッチ、Alpine Linux ベース（~5MB の小さい base）。
FROM node:24-alpine

# tsx: TypeScript ファイルを直接実行するランナー（ts-node の代替）。
# vitest: テストランナー。採点ジョブで `vitest run --reporter=json` を実行する想定。
RUN npm install -g tsx vitest

# /sandbox: ジョブごとに solution.ts と test.ts を volume mount する作業ディレクトリ。
WORKDIR /sandbox

# node ユーザ: Alpine 公式 node イメージに既存の非 root ユーザ（uid 1000）。
# 採点コンテナはこの非 root で動かす（--user 1000:1000）。
USER node

# ENTRYPOINT は tsx 固定。実際の test 実行は採点ジョブごとに volume mount + 引数で指定する
# （例：docker run --rm -v ./solution.ts:/sandbox/solution.ts ... sandbox vitest run ...）。
ENTRYPOINT ["tsx"]
