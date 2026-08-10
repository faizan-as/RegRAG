import type { User } from "@supabase/supabase-js";

export function getUserDisplayRole(user: User | null): string {
  const roles = user?.app_metadata?.roles;
  if (!Array.isArray(roles) || roles.length === 0) {
    return "researcher";
  }

  const role = roles.find((value) => typeof value === "string" && value.trim());
  return role ? role.toLowerCase() : "researcher";
}
