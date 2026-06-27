// Cross-browser WebExtension namespace. Chrome exposes `chrome.*`; Safari and
// Firefox expose a promise-based `browser.*`. Modern Chrome (MV3) also returns
// promises for most APIs when no callback is passed, so promise-style usage
// works on both targets.
export const api =
  typeof globalThis.browser !== "undefined" && globalThis.browser?.runtime
    ? globalThis.browser
    : globalThis.chrome;
