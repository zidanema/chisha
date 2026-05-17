// @chisha/contracts — shared types between Living (apps/web) + Lab (apps/debug-ui).
//
// D-085 invariant 8 (refactor_living_lab.md §7):
//   "共享只到 packages/contracts/ (trace types + API client fetch helper), UI 不共享.
//    改 Living API 字段时, contracts 类型同步, 两边 Vite tsc 立刻飘红."

export * from "./living";
export * from "./trace";
