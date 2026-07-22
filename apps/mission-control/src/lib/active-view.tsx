"use client";

import { createContext, useContext } from "react";

export type ActiveViewCtxType = {
  active: string;
  setActive: (id: string) => void;
};

export const ActiveViewCtx = createContext<ActiveViewCtxType>({
  active: "overview",
  setActive: () => {},
});

export function useActiveView() {
  return useContext(ActiveViewCtx);
}
