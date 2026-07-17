import { create } from "zustand";

export const usePhaseStore = create((set) => ({
  phase: "intro", // "intro" | "assistant"
  introOffset: 0,
  enterAssistant: () => set({ phase: "assistant" }),
  setIntroOffset: (introOffset) => set({ introOffset }),
}));
