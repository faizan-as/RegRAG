"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { AlertCircleIcon, KeyRoundIcon, LogInIcon, MailIcon } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { createSupabaseBrowserClient } from "@/lib/supabase/browser";

type LoginFormProps = {
  nextPath: string;
  isConfigured: boolean;
  missingKeys: string[];
};

export function LoginForm({ nextPath, isConfigured, missingKeys }: LoginFormProps) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [mode, setMode] = useState<"login" | "reset">("login");
  const [isBusy, setIsBusy] = useState(false);
  const router = useRouter();

  const configMessage = useMemo(() => {
    if (isConfigured) {
      return null;
    }
    return `Missing configuration: ${missingKeys.join(", ")}`;
  }, [isConfigured, missingKeys]);

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (!isConfigured) {
      toast.error("Authentication is unavailable until public environment variables are configured.");
      return;
    }

    setIsBusy(true);

    try {
      const supabase = createSupabaseBrowserClient();

      if (mode === "login") {
        const { error } = await supabase.auth.signInWithPassword({ email, password });
        if (error) {
          toast.error(error.message);
          return;
        }

        toast.success("Signed in.");
        router.replace(nextPath);
        router.refresh();
        return;
      }

      const { error } = await supabase.auth.resetPasswordForEmail(email, {
        redirectTo: `${window.location.origin}/auth/callback?next=/login`,
      });
      if (error) {
        toast.error(error.message);
        return;
      }

      toast.success("Password reset email sent.");
    } finally {
      setIsBusy(false);
    }
  }

  return (
    <div className="w-full max-w-md rounded-lg border border-border bg-card p-5 shadow-sm">
      <div className="mb-4 space-y-1">
        <h1 className="text-xl font-semibold">Regulatory Workspace Login</h1>
        <p className="text-sm text-muted-foreground">Use your approved account to access research workflows.</p>
      </div>

      {configMessage ? (
        <Alert variant="destructive" className="mb-4">
          <AlertCircleIcon className="size-4" />
          <AlertTitle>Configuration required</AlertTitle>
          <AlertDescription>{configMessage}</AlertDescription>
        </Alert>
      ) : null}

      <form className="space-y-4" onSubmit={handleSubmit}>
        <div className="space-y-1.5">
          <Label htmlFor="email">Email</Label>
          <Input
            id="email"
            type="email"
            autoComplete="email"
            required
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            placeholder="name@company.com"
          />
        </div>

        {mode === "login" ? (
          <div className="space-y-1.5">
            <Label htmlFor="password">Password</Label>
            <Input
              id="password"
              type="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              placeholder="Enter password"
            />
          </div>
        ) : null}

        <Button type="submit" className="h-9 w-full" disabled={isBusy}>
          {mode === "login" ? <LogInIcon className="size-4" /> : <MailIcon className="size-4" />}
          {mode === "login" ? "Sign in" : "Send reset email"}
        </Button>
      </form>

      <div className="mt-4 flex items-center justify-between text-sm">
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="h-7"
          onClick={() => setMode(mode === "login" ? "reset" : "login")}
        >
          <KeyRoundIcon className="size-4" />
          {mode === "login" ? "Forgot password" : "Back to login"}
        </Button>
        <span className="text-xs text-muted-foreground">Secure session cookies only</span>
      </div>
    </div>
  );
}
