import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import * as Notifications from "expo-notifications";
import { Stack, router } from "expo-router";
import { StatusBar } from "expo-status-bar";
import { useEffect, useState } from "react";
import { SafeAreaProvider } from "react-native-safe-area-context";

import { routeForLink } from "../src/lib/push";
import { SessionProvider } from "../src/lib/session";

export default function RootLayout() {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 30_000,
            retry: (count, err) => {
              const status = (err as { status?: number }).status;
              return !(status && status >= 400 && status < 500) && count < 2;
            },
          },
        },
      }),
  );

  useEffect(() => {
    const sub = Notifications.addNotificationResponseReceivedListener((res) => {
      const route = routeForLink(res.notification.request.content.data?.link);
      if (route) router.push(route);
    });
    return () => sub.remove();
  }, []);

  return (
    <SafeAreaProvider>
      <QueryClientProvider client={queryClient}>
        <SessionProvider>
          <StatusBar style="dark" />
          <Stack>
            <Stack.Screen name="(tabs)" options={{ headerShown: false }} />
            <Stack.Screen name="login" options={{ headerShown: false }} />
            <Stack.Screen name="visit/new" options={{ title: "New visit", presentation: "modal" }} />
            <Stack.Screen name="visit/[id]" options={{ title: "Site visit" }} />
            <Stack.Screen name="property/[id]" options={{ title: "Property" }} />
            <Stack.Screen name="task/new" options={{ title: "New task", presentation: "modal" }} />
          </Stack>
        </SessionProvider>
      </QueryClientProvider>
    </SafeAreaProvider>
  );
}
