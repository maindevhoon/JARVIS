import { create } from "zustand";

export const usePhaseStore = create((set) => ({
  phase: "assistant", // the workspace should be immediately usable
  introOffset: 0,
  enterAssistant: () => set({ phase: "assistant" }),
  setIntroOffset: (introOffset) => set({ introOffset }),
}));
