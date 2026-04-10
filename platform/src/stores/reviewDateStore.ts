import { create } from 'zustand';

interface ReviewDateState {
  /** ISO date string (YYYY-MM-DD) when reviewing historical data. null = live mode. */
  reviewDate: string | null;
  /** Optional time string (HH:MM, 24h ET). null = end of trading day. */
  reviewTime: string | null;
  setReviewDate: (date: string | null) => void;
  setReviewTime: (time: string | null) => void;
  clearReviewDate: () => void;
}

export const useReviewDateStore = create<ReviewDateState>((set) => ({
  reviewDate: null,
  reviewTime: null,
  setReviewDate: (date) => set({ reviewDate: date }),
  setReviewTime: (time) => set({ reviewTime: time }),
  clearReviewDate: () => set({ reviewDate: null, reviewTime: null }),
}));
