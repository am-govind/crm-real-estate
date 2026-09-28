import * as Location from "expo-location";

import type { Fix } from "./offline";

/** Current GPS fix, or null when permission is denied. Falls back to the last known position when a fresh fix times out. */
export async function currentFix(): Promise<Fix | null> {
  const { status } = await Location.requestForegroundPermissionsAsync();
  if (status !== "granted") return null;
  const toFix = (p: Location.LocationObject): Fix => ({
    latitude: p.coords.latitude,
    longitude: p.coords.longitude,
    accuracy_m: p.coords.accuracy ?? undefined,
  });
  try {
    const pos = await Promise.race([
      Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.High }),
      new Promise<never>((_, reject) => setTimeout(() => reject(new Error("timeout")), 15_000)),
    ]);
    return toFix(pos);
  } catch {
    const last = await Location.getLastKnownPositionAsync();
    return last ? toFix(last) : null;
  }
}
