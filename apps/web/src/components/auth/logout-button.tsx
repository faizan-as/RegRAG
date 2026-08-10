"use client";

import { LogOutIcon } from "lucide-react";
import { Button } from "@/components/ui/button";

export function LogoutButton() {
  return (
    <form action="/auth/logout" method="post" className="w-full">
      <Button
        type="submit"
        variant="ghost"
        className="h-8 w-full justify-start"
      >
        <LogOutIcon className="size-4" />
        Sign out
      </Button>
    </form>
  );
}
