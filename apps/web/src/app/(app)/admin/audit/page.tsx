import { redirect } from "next/navigation";
import { createSupabaseServerClient } from "@/lib/supabase/server";
import { getUserDisplayRole } from "@/lib/auth/session";
import { AuditWorkspace } from "@/components/admin/audit-workspace";

export default async function AuditPage() {
  const supabase = await createSupabaseServerClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  if (getUserDisplayRole(user) !== "admin") {
    redirect("/research");
  }

  return <AuditWorkspace />;
}
