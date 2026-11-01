const path = require("node:path");
const root = process.argv[2];
const sqlitePath = path.join(root, "resources/app.asar/node_modules/better-sqlite3");
console.error("stage: require better-sqlite3");
const Database = require(sqlitePath);
console.error("stage: open memory database");
const db = new Database(":memory:");
console.error("stage: create normal and FTS5 tables");
db.exec("CREATE TABLE t(body TEXT); CREATE VIRTUAL TABLE f USING fts5(body);");
console.error("stage: insert rows");
db.prepare("INSERT INTO t VALUES (?)").run("issue 3038 scratch probe");
db.prepare("INSERT INTO f VALUES (?)").run("issue 3038 scratch probe");
console.error("stage: select rows");
console.log(JSON.stringify({
  versions: process.versions,
  betterSqlite3: require(path.join(sqlitePath, "package.json")).version,
  sqlite: db.prepare("SELECT sqlite_version() AS version").get(),
  rows: db.prepare("SELECT count(*) AS count FROM t").get(),
  fts: db.prepare("SELECT body FROM f WHERE f MATCH 'scratch'").all(),
  json: db.prepare("SELECT json_extract('{\"probe\":true}', '$.probe') AS value").get(),
}));
db.close();
