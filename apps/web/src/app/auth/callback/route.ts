import { NextResponse } from "next/server";
import { createSupabaseServerClient } from "@/lib/supabase/server";
import { normalizeRelativeNextPath } from "@/lib/auth/next-path";

export async function GET(request: Request) {
  const url = new URL(request.url);
  const code = url.searchParams.get("code");
  const nextPath = normalizeRelativeNextPath(url.searchParams.get("next"));

  if (!code) {
    return NextResponse.redirect(new URL("/login?error=missing_code", url.origin));
  }

  try {
    const supabase = await createSupabaseServerClient();
    const { error } = await supabase.auth.exchangeCodeForSession(code);

    if (error) {
      return NextResponse.redirect(new URL(`/login?error=${encodeURIComponent("auth_callback_failed")}`, url.origin));
    }

    return NextResponse.redirect(new URL(nextPath, url.origin));
  } catch {
    return NextResponse.redirect(new URL("/login?error=missing_config", url.origin));
  }
}
