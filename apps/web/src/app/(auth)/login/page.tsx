import { LoginForm } from "@/components/auth/login-form";
import { getPublicConfigState } from "@/lib/env";
import { normalizeRelativeNextPath } from "@/lib/auth/next-path";

type LoginPageProps = {
  searchParams: Promise<{ next?: string; error?: string }>;
};

export default async function LoginPage({ searchParams }: LoginPageProps) {
  const params = await searchParams;
  const nextPath = normalizeRelativeNextPath(params.next);
  const config = getPublicConfigState();

  return (
    <main className="mx-auto flex min-h-svh max-w-[1200px] items-center justify-center px-3 py-8">
      <div className="grid w-full place-items-center">
        <LoginForm
          nextPath={nextPath}
          isConfigured={config.isConfigured}
          missingKeys={config.missing as string[]}
        />
      </div>
    </main>
  );
}
