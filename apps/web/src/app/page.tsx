import { redirect } from "next/navigation";
import { getPublicConfigState } from "@/lib/env";
import { createSupabaseServerClient } from "@/lib/supabase/server";

export default async function Home() {
  const config = getPublicConfigState();
  if (!config.isConfigured) {
    redirect("/login");
  }

  const supabase = await createSupabaseServerClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  if (user) {
    redirect("/research");
  }

  redirect("/login");
}
