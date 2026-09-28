import { createApiClient } from "@landcrm/api-client";

import { API_BASE_URL } from "./config";
import { getAccessToken, getTenantId, notifySignedOut } from "./tokens";

export const api = createApiClient({
  baseUrl: API_BASE_URL,
  mode: "bearer",
  getAccessToken,
  getTenantId,
  onUnauthorized: notifySignedOut,
});
