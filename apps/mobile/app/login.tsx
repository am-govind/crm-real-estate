import { Redirect } from "expo-router";
import { useState } from "react";
import { View } from "react-native";

import { Body, Button, Card, Loading, Muted, Screen, Title } from "../src/components/ui";
import { DEV_AUTH_EMAIL } from "../src/lib/config";
import { useSession } from "../src/lib/session";

export default function LoginScreen() {
  const { status, me, error, signIn, signOut, chooseTenant } = useSession();
  const [busy, setBusy] = useState(false);

  if (status === "ready") return <Redirect href="/" />;
  if (status === "loading") return <Loading />;

  if (status === "chooseTenant" && me) {
    return (
      <Screen>
        <Title>Choose organisation</Title>
        <Muted>You belong to more than one organisation. Field data is kept separately for each.</Muted>
        {me.memberships.map((m) => (
          <Card key={m.tenant_id} onPress={() => void chooseTenant(m.tenant_id)}>
            <Body>{m.tenant_name}</Body>
            <Muted>{m.role_keys.join(", ")}</Muted>
          </Card>
        ))}
        <Button kind="secondary" title="Sign out" onPress={() => void signOut()} />
      </Screen>
    );
  }

  return (
    <Screen>
      <View style={{ gap: 12, marginTop: 80 }}>
        <Title>Land Deal CRM</Title>
        <Muted>Field app for site visits, tasks and assigned properties. Works offline once signed in.</Muted>
        {error ? <Body>{error}</Body> : null}
        <Button
          title={DEV_AUTH_EMAIL ? `Sign in as ${DEV_AUTH_EMAIL} (dev)` : "Sign in"}
          busy={busy}
          onPress={async () => {
            setBusy(true);
            try {
              await signIn();
            } finally {
              setBusy(false);
            }
          }}
        />
      </View>
    </Screen>
  );
}
