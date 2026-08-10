import { z } from "zod";

const publicEnvSchema = z.object({
  NEXT_PUBLIC_API_BASE_URL: z.string().trim().url().optional(),
  NEXT_PUBLIC_SUPABASE_URL: z.string().trim().url().optional(),
  NEXT_PUBLIC_SUPABASE_ANON_KEY: z.string().trim().min(1).optional(),
});

type PublicEnv = z.infer<typeof publicEnvSchema>;

export type PublicConfigState = {
  isConfigured: boolean;
  missing: Array<keyof PublicEnv>;
  values: PublicEnv;
};

export function getPublicConfigState(): PublicConfigState {
  const parsed = publicEnvSchema.safeParse({
    NEXT_PUBLIC_API_BASE_URL: process.env.NEXT_PUBLIC_API_BASE_URL,
    NEXT_PUBLIC_SUPABASE_URL: process.env.NEXT_PUBLIC_SUPABASE_URL,
    NEXT_PUBLIC_SUPABASE_ANON_KEY: process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY,
  });

  if (!parsed.success) {
    const requiredKeys: Array<keyof PublicEnv> = [
      "NEXT_PUBLIC_API_BASE_URL",
      "NEXT_PUBLIC_SUPABASE_URL",
      "NEXT_PUBLIC_SUPABASE_ANON_KEY",
    ];
    const missing = requiredKeys.filter((key) => {
      const raw = process.env[key];
      return !raw || !raw.trim();
    });
    return {
      isConfigured: false,
      missing,
      values: {
        NEXT_PUBLIC_API_BASE_URL: process.env.NEXT_PUBLIC_API_BASE_URL,
        NEXT_PUBLIC_SUPABASE_URL: process.env.NEXT_PUBLIC_SUPABASE_URL,
        NEXT_PUBLIC_SUPABASE_ANON_KEY: process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY,
      },
    };
  }

  const requiredKeys: Array<keyof PublicEnv> = [
    "NEXT_PUBLIC_API_BASE_URL",
    "NEXT_PUBLIC_SUPABASE_URL",
    "NEXT_PUBLIC_SUPABASE_ANON_KEY",
  ];
  const missing = requiredKeys.filter((key) => {
    const value = parsed.data[key];
    return !value || !value.trim();
  });

  return {
    isConfigured: missing.length === 0,
    missing,
    values: parsed.data,
  };
}

function requireConfiguredValue<K extends keyof PublicEnv>(
  key: K,
  configState: PublicConfigState,
): NonNullable<PublicEnv[K]> {
  const value = configState.values[key];
  if (!value || !value.trim()) {
    throw new Error(`Missing required public configuration: ${key}`);
  }
  return value as NonNullable<PublicEnv[K]>;
}

export function getRequiredPublicEnv() {
  const state = getPublicConfigState();
  return {
    NEXT_PUBLIC_API_BASE_URL: requireConfiguredValue("NEXT_PUBLIC_API_BASE_URL", state),
    NEXT_PUBLIC_SUPABASE_URL: requireConfiguredValue("NEXT_PUBLIC_SUPABASE_URL", state),
    NEXT_PUBLIC_SUPABASE_ANON_KEY: requireConfiguredValue("NEXT_PUBLIC_SUPABASE_ANON_KEY", state),
  };
}
