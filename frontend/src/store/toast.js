// src/store/toast.js
import { create } from 'zustand'

let nextId = 1

const useToastStore = create((set) => ({
  toasts: [],

  addToast: (message, type = 'success', duration = 3500) => {
    const id = nextId++
    set((state) => ({
      toasts: [...state.toasts, { id, message, type, duration }],
    }))
    setTimeout(() => {
      set((state) => ({ toasts: state.toasts.filter((t) => t.id !== id) }))
    }, duration)
  },

  removeToast: (id) =>
    set((state) => ({ toasts: state.toasts.filter((t) => t.id !== id) })),
}))

export default useToastStore

// Convenience helpers — import these in components
export const toast = {
  success: (msg) => useToastStore.getState().addToast(msg, 'success'),
  error: (msg) => useToastStore.getState().addToast(msg, 'error', 5000),
  info: (msg) => useToastStore.getState().addToast(msg, 'info'),
  warning: (msg) => useToastStore.getState().addToast(msg, 'warning', 4000),
}
