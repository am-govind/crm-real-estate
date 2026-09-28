import Constants from "expo-constants";
import * as Device from "expo-device";
import * as Notifications from "expo-notifications";
import * as SecureStore from "expo-secure-store";
import { Platform } from "react-native";

import { api } from "./api";

const PUSH_TOKEN_KEY = "landcrm.pushToken";

Notifications.setNotificationHandler({
  handleNotification: async () => ({ shouldShowAlert: true, shouldPlaySound: false, shouldSetBadge: false }),
});

/** Registers this device's Expo push token with the API. Silently no-ops on simulators or when denied. */
export async function registerForPush() {
  if (!Device.isDevice) return;
  if (Platform.OS === "android") {
    await Notifications.setNotificationChannelAsync("default", { name: "Default", importance: Notifications.AndroidImportance.DEFAULT });
  }
  let { status } = await Notifications.getPermissionsAsync();
  if (status !== "granted") ({ status } = await Notifications.requestPermissionsAsync());
  if (status !== "granted") return;
  const projectId = Constants.expoConfig?.extra?.eas?.projectId ?? Constants.easConfig?.projectId;
  const { data: token } = await Notifications.getExpoPushTokenAsync(projectId ? { projectId } : undefined);
  await api.notifications.registerDevice(token, Platform.OS === "ios" ? "ios" : "android");
  await SecureStore.setItemAsync(PUSH_TOKEN_KEY, token);
}

export async function unregisterPush() {
  const token = await SecureStore.getItemAsync(PUSH_TOKEN_KEY);
  if (!token) return;
  try {
    await api.notifications.unregisterDevice(token);
  } finally {
    await SecureStore.deleteItemAsync(PUSH_TOKEN_KEY);
  }
}

/** Notification payloads carry the in-app link (e.g. /site-visits/<id>); map it to a mobile route. */
export function routeForLink(link: unknown): string | null {
  if (typeof link !== "string") return null;
  const visit = link.match(/^\/site-visits\/([\w-]+)/);
  if (visit) return `/visit/${visit[1]}`;
  const property = link.match(/^\/properties\/([\w-]+)/);
  if (property) return `/property/${property[1]}`;
  if (link.startsWith("/tasks")) return "/tasks";
  return null;
}
