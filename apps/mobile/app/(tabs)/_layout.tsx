import { colors } from "@landcrm/ui";
import { Redirect, Tabs } from "expo-router";

import { Loading } from "../../src/components/ui";
import { useSession } from "../../src/lib/session";

export default function TabsLayout() {
  const { status } = useSession();
  if (status === "loading") return <Loading />;
  if (status !== "ready") return <Redirect href="/login" />;
  return (
    <Tabs screenOptions={{ tabBarActiveTintColor: colors.primary, headerTitleStyle: { fontWeight: "600" } }}>
      <Tabs.Screen name="index" options={{ title: "Today" }} />
      <Tabs.Screen name="visits" options={{ title: "Visits" }} />
      <Tabs.Screen name="properties" options={{ title: "Properties" }} />
      <Tabs.Screen name="tasks" options={{ title: "Tasks" }} />
    </Tabs>
  );
}
