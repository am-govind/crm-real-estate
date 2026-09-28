import { colors, font, radius, space, statusTone, tones } from "@landcrm/ui";
import type { ReactNode } from "react";
import {
  ActivityIndicator,
  Pressable,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
  type TextInputProps,
  type ViewStyle,
} from "react-native";

import { useOffline } from "../lib/offline";

export function Screen({ children, onRefresh, refreshing = false }: { children: ReactNode; onRefresh?: () => void; refreshing?: boolean }) {
  return (
    <ScrollView
      style={styles.screen}
      contentContainerStyle={styles.screenContent}
      keyboardShouldPersistTaps="handled"
      refreshControl={onRefresh ? <RefreshControl refreshing={refreshing} onRefresh={onRefresh} /> : undefined}
    >
      <SyncBanner />
      {children}
    </ScrollView>
  );
}

export function Card({ children, onPress, style }: { children: ReactNode; onPress?: () => void; style?: ViewStyle }) {
  if (onPress) {
    return (
      <Pressable onPress={onPress} style={({ pressed }) => [styles.card, pressed && { opacity: 0.7 }, style]}>
        {children}
      </Pressable>
    );
  }
  return <View style={[styles.card, style]}>{children}</View>;
}

export function Title({ children }: { children: ReactNode }) {
  return <Text style={styles.title}>{children}</Text>;
}

export function Heading({ children }: { children: ReactNode }) {
  return <Text style={styles.heading}>{children}</Text>;
}

export function Muted({ children }: { children: ReactNode }) {
  return <Text style={styles.muted}>{children}</Text>;
}

export function Body({ children }: { children: ReactNode }) {
  return <Text style={styles.body}>{children}</Text>;
}

export function Row({ children, style }: { children: ReactNode; style?: ViewStyle }) {
  return <View style={[styles.row, style]}>{children}</View>;
}

type ButtonKind = "primary" | "secondary" | "danger";

export function Button({ title, onPress, kind = "primary", disabled, busy }: { title: string; onPress: () => void; kind?: ButtonKind; disabled?: boolean; busy?: boolean }) {
  const bg = kind === "primary" ? colors.primary : kind === "danger" ? colors.danger : colors.surface;
  const fg = kind === "secondary" ? colors.text : colors.primaryText;
  return (
    <Pressable
      accessibilityRole="button"
      disabled={disabled || busy}
      onPress={onPress}
      style={({ pressed }) => [styles.button, { backgroundColor: bg, opacity: disabled ? 0.5 : pressed ? 0.8 : 1 }, kind === "secondary" && styles.buttonSecondary]}
    >
      {busy ? <ActivityIndicator color={fg} /> : <Text style={[styles.buttonText, { color: fg }]}>{title}</Text>}
    </Pressable>
  );
}

export function Badge({ label, status }: { label: string; status?: string }) {
  const tone = tones[statusTone(status ?? label)];
  return (
    <View style={[styles.badge, { backgroundColor: tone.bg }]}>
      <Text style={[styles.badgeText, { color: tone.fg }]}>{label.replace(/_/g, " ")}</Text>
    </View>
  );
}

export function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <View style={styles.field}>
      <Text style={styles.label}>{label}</Text>
      {children}
    </View>
  );
}

export function Input(props: TextInputProps) {
  return <TextInput placeholderTextColor={colors.textMuted} {...props} style={[styles.input, props.multiline && styles.inputMultiline, props.style]} />;
}

export function Choice<T extends string>({ value, options, onChange }: { value: T; options: { value: T; label: string }[]; onChange: (v: T) => void }) {
  return (
    <View style={styles.choices}>
      {options.map((o) => (
        <Pressable key={o.value} onPress={() => onChange(o.value)} style={[styles.choice, o.value === value && styles.choiceActive]}>
          <Text style={[styles.choiceText, o.value === value && styles.choiceTextActive]}>{o.label}</Text>
        </Pressable>
      ))}
    </View>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return (
    <View style={styles.empty}>
      <Text style={styles.muted}>{children}</Text>
    </View>
  );
}

export function Loading() {
  return (
    <View style={styles.empty}>
      <ActivityIndicator color={colors.primary} />
    </View>
  );
}

function SyncBanner() {
  const online = useOffline((s) => s.online);
  const queued = useOffline((s) => s.outbox.length + s.media.length);
  const failed = useOffline((s) => s.failed.length);
  if (online && !queued && !failed) return null;
  const tone = failed ? tones.danger : online ? tones.info : tones.warning;
  const text = [
    !online && "Offline",
    queued && `${queued} change${queued === 1 ? "" : "s"} waiting to sync`,
    failed && `${failed} change${failed === 1 ? "" : "s"} rejected (see Today)`,
  ].filter(Boolean).join(" · ");
  return (
    <View style={[styles.banner, { backgroundColor: tone.bg }]}>
      <Text style={{ color: tone.fg, fontSize: font.size.sm }}>{text}</Text>
    </View>
  );
}

export function formatDateTime(iso: string | null | undefined) {
  if (!iso) return "—";
  return new Date(iso).toLocaleString(undefined, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}

export function formatDate(iso: string | null | undefined) {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}

export const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.bg },
  screenContent: { padding: space.lg, gap: space.md, paddingBottom: space.xxl * 2 },
  card: { backgroundColor: colors.surface, borderRadius: radius.lg, borderWidth: 1, borderColor: colors.border, padding: space.lg, gap: space.sm },
  title: { fontSize: font.size.xxl, fontWeight: "700", color: colors.text },
  heading: { fontSize: font.size.lg, fontWeight: "600", color: colors.text },
  body: { fontSize: font.size.md, color: colors.text },
  muted: { fontSize: font.size.sm, color: colors.textMuted },
  row: { flexDirection: "row", alignItems: "center", gap: space.sm, flexWrap: "wrap" },
  button: { paddingVertical: space.md, paddingHorizontal: space.lg, borderRadius: radius.md, alignItems: "center", justifyContent: "center", minHeight: 44 },
  buttonSecondary: { borderWidth: 1, borderColor: colors.border },
  buttonText: { fontSize: font.size.md, fontWeight: "600" },
  badge: { paddingHorizontal: space.sm, paddingVertical: 2, borderRadius: radius.pill, alignSelf: "flex-start" },
  badgeText: { fontSize: font.size.xs, fontWeight: "600", textTransform: "capitalize" },
  field: { gap: space.xs },
  label: { fontSize: font.size.sm, fontWeight: "500", color: colors.textMuted },
  input: {
    borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, paddingHorizontal: space.md, paddingVertical: space.sm,
    fontSize: font.size.md, color: colors.text, backgroundColor: colors.surface, minHeight: 44,
  },
  inputMultiline: { minHeight: 88, textAlignVertical: "top" },
  choices: { flexDirection: "row", flexWrap: "wrap", gap: space.sm },
  choice: { borderWidth: 1, borderColor: colors.border, borderRadius: radius.pill, paddingHorizontal: space.md, paddingVertical: space.xs, backgroundColor: colors.surface },
  choiceActive: { backgroundColor: colors.primary, borderColor: colors.primary },
  choiceText: { fontSize: font.size.sm, color: colors.text },
  choiceTextActive: { color: colors.primaryText },
  empty: { padding: space.xl, alignItems: "center" },
  banner: { padding: space.sm, borderRadius: radius.md },
});
