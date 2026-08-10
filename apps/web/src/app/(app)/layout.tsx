import { headers } from "next/headers";
import { redirect } from "next/navigation";
import { AppShell } from "@/components/app-shell/app-shell";
import { createSupabaseServerClient } from "@/lib/supabase/server";
import { getPublicConfigState } from "@/lib/env";
import { getUserDisplayRole } from "@/lib/auth/session";

export default async function ProtectedLayout({ children }: { children: React.ReactNode }) {
  const config = getPublicConfigState();
  const headerStore = await headers();
  const pathname = headerStore.get("x-pathname") ?? "/research";

  if (!config.isConfigured) {
    redirect("/login");
  }

  const supabase = await createSupabaseServerClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  if (!user) {
    redirect(`/login?next=${encodeURIComponent(pathname)}`);
  }

  const role = getUserDisplayRole(user);

  return <AppShell email={user.email ?? "unknown"} role={role}>{children}</AppShell>;
}
