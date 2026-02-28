import { create } from 'zustand';
import { persist } from 'zustand/middleware';

export type LayoutType = 'mosaic' | 'icons' | 'sidebar' | 'ai-centric';

interface DesignStore {
  layout: LayoutType;
  setLayout: (layout: LayoutType) => void;
}

export const useDesignStore = create<DesignStore>()(
  persist(
    (set) => ({
      layout: 'mosaic',
      setLayout: (layout) => set({ layout }),
    }),
    {
      name: 'glame-design-preferences',
    }
  )
);