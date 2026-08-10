"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  BellRingIcon,
  ChevronDownIcon,
  FileSearchIcon,
  FlaskConicalIcon,
  MenuIcon,
  MessageSquareTextIcon,
  ShieldCheckIcon,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { LogoutButton } from "@/components/auth/logout-button";
import { ApiStatusIndicator } from "@/components/app-shell/api-status-indicator";
import { DisplayRoleProvider } from "@/components/app-shell/display-role-context";

type AppShellProps = {
  email: string;
  role: string;
  children: React.ReactNode;
};

type NavItem = {
  href: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
};

const primaryNav: NavItem[] = [
  { href: "/research", label: "Research", icon: FlaskConicalIcon },
  { href: "/search", label: "Search", icon: FileSearchIcon },
  { href: "/chat", label: "Chat", icon: MessageSquareTextIcon },
  { href: "/alerts", label: "Alerts", icon: BellRingIcon },
];

function NavLinks({ items, pathname, className }: { items: NavItem[]; pathname: string; className?: string }) {
  return (
    <nav className={cn("space-y-1", className)} aria-label="Workspace">
      {items.map((item) => {
        const Icon = item.icon;
        const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
        return (
          <Link
            key={item.href}
            href={item.href}
            className={cn(
              "flex h-9 items-center gap-2 rounded-md border px-2.5 text-sm transition-colors",
              active
                ? "border-primary/40 bg-primary/10 text-primary"
                : "border-transparent text-muted-foreground hover:border-border hover:bg-muted/50 hover:text-foreground",
            )}
          >
            <Icon className="size-4" />
            <span>{item.label}</span>
          </Link>
        );
      })}
    </nav>
  );
}

export function AppShell({ email, role, children }: AppShellProps) {
  const pathname = usePathname();
  const showAudit = role === "admin";

  return (
    <DisplayRoleProvider role={role}>
      <div className="min-h-svh">
        <div className="mx-auto grid max-w-[1200px] grid-cols-1 gap-3 p-3 md:grid-cols-[220px_1fr] md:p-4">
        <aside className="hidden rounded-lg border border-sidebar-border bg-sidebar p-3 md:block">
          <div className="mb-3 flex h-8 items-center justify-between">
            <p className="font-semibold tracking-tight">Regulatory Ops</p>
            <Badge variant="outline" className="h-5">MVP</Badge>
          </div>
          <NavLinks items={primaryNav} pathname={pathname} />
          {showAudit ? (
            <div className="mt-2 border-t border-border pt-2">
              <Link
                href="/admin/audit"
                className={cn(
                  "flex h-9 items-center gap-2 rounded-md border px-2.5 text-sm transition-colors",
                  pathname.startsWith("/admin/audit")
                    ? "border-primary/40 bg-primary/10 text-primary"
                    : "border-transparent text-muted-foreground hover:border-border hover:bg-muted/50 hover:text-foreground",
                )}
              >
                <ShieldCheckIcon className="size-4" />
                Audit
              </Link>
            </div>
          ) : null}
        </aside>

        <div className="space-y-3">
          <header className="flex h-10 items-center justify-between rounded-lg border border-border bg-surface-raised px-2.5">
            <div className="flex items-center gap-2">
              <Sheet>
                <SheetTrigger render={<Button variant="outline" size="icon-sm" className="md:hidden" />}>
                  <MenuIcon className="size-4" />
                  <span className="sr-only">Open navigation</span>
                </SheetTrigger>
                <SheetContent side="left" className="w-[240px] p-0">
                  <SheetHeader className="border-b border-border">
                    <SheetTitle>Regulatory Ops</SheetTitle>
                  </SheetHeader>
                  <div className="p-3">
                    <NavLinks items={primaryNav} pathname={pathname} />
                    {showAudit ? (
                      <div className="mt-2 border-t border-border pt-2">
                        <Link
                          href="/admin/audit"
                          className="flex h-9 items-center gap-2 rounded-md border border-transparent px-2.5 text-sm text-muted-foreground hover:border-border hover:bg-muted/50 hover:text-foreground"
                        >
                          <ShieldCheckIcon className="size-4" />
                          Audit
                        </Link>
                      </div>
                    ) : null}
                  </div>
                </SheetContent>
              </Sheet>
              <ApiStatusIndicator />
            </div>

            <DropdownMenu>
              <DropdownMenuTrigger render={<Button variant="outline" size="sm" className="h-8" />}>
                Account
                <ChevronDownIcon className="size-4" />
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" sideOffset={8} className="w-64">
                <DropdownMenuLabel className="space-y-1">
                  <div className="truncate text-sm font-medium text-foreground">{email}</div>
                  <div className="text-xs text-muted-foreground">Role hint: {role}</div>
                </DropdownMenuLabel>
                <DropdownMenuSeparator />
                <DropdownMenuItem render={<div className="w-full" />}>
                  <LogoutButton />
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </header>

          <main>{children}</main>
        </div>
        </div>
      </div>
    </DisplayRoleProvider>
  );
}
