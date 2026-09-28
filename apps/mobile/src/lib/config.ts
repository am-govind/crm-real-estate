export const API_BASE_URL = process.env.EXPO_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
export const OIDC_ISSUER = process.env.EXPO_PUBLIC_OIDC_ISSUER ?? "http://localhost:8080/realms/landcrm";
export const OIDC_CLIENT_ID = process.env.EXPO_PUBLIC_OIDC_CLIENT_ID ?? "landcrm-mobile";
export const OIDC_SCOPES = ["openid", "profile", "email", "offline_access"];
/** When set, sign-in skips OIDC and uses the API's dev auth provider (`LANDCRM_AUTH_MODE=dev`). */
export const DEV_AUTH_EMAIL = process.env.EXPO_PUBLIC_DEV_AUTH_EMAIL ?? "";
