// D-085: types canonical 定义已迁到 @chisha/contracts/living.
// 旧 import 路径仍可用 — apps/web 内部代码继续从 @/lib/types 拿是 OK 的,
// 实际值/类型走 contracts. 改字段时改 packages/contracts/src/living.ts.

export * from "@chisha/contracts/living";
