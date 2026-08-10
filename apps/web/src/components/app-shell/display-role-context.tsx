"use client";

import { createContext, useContext } from "react";

const DisplayRoleContext = createContext({ role: "researcher" });

export function DisplayRoleProvider({
  role,
  children,
}: {
  role: string;
  children: React.ReactNode;
}) {
  return <DisplayRoleContext.Provider value={{ role }}>{children}</DisplayRoleContext.Provider>;
}

export function useDisplayRole() {
  return useContext(DisplayRoleContext);
}