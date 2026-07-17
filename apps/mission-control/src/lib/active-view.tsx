"use client";

import { createContext, useContext } from "react";

export const ActiveViewCtx = createContext<string>("overview");

export function useActiveView() {
  return useContext(ActiveViewCtx);
}
