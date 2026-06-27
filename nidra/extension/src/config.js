// Nidra extension config.
//
// These defaults are BAKED FROM THE PROJECT'S ROOT .env AT BUILD TIME (see
// build.mjs): backendUrl from APP_PORT, appToken from API_AUTH_TOKEN. So .env is
// the single source of truth — run `npm run build` after changing it. A browser
// extension can't read .env at runtime (it's sandboxed), hence build-time baking.
// Anything a user sets via the popup/storage still overrides these.
export const DEFAULTS = {
  backendUrl:
    typeof __NIDRA_BACKEND_URL__ !== "undefined" ? __NIDRA_BACKEND_URL__ : "http://localhost:8088",
  appToken: typeof __NIDRA_APP_TOKEN__ !== "undefined" ? __NIDRA_APP_TOKEN__ : "dev-token",
};
