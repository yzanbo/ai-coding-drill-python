// syncpack 設定（ADR 0024）。apps/web は単一 package.json 構成なので、
// バージョン整合性ではなく「package.json の書式整合」だけを担保する 3 ルール構成（ADR 0024 Note）。
// 詳細: https://jamiemason.github.io/syncpack/config/rc-file/
import type { RcFile } from "syncpack";

const config: RcFile = {
  // sortPackages: package.json のトップレベルキー順を一定にする。
  sortPackages: true,
  // sortFirst: package.json 内の重要キーを先頭に固定。
  sortFirst: ["name", "version", "private", "type", "scripts"],
  // sortAz: 各 dependencies 系オブジェクトのキーをアルファベット順に整える。
  sortAz: ["dependencies", "devDependencies", "peerDependencies", "optionalDependencies"],
  // versionGroups: 単一 package.json では実質不要だが、空配列を明示しておく。
  versionGroups: [],
  // semverGroups: 同上。
  semverGroups: [],
};

export default config;
