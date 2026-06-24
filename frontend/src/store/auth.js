import { create } from 'zustand'
import { persist } from 'zustand/middleware'

const useAuthStore = create(
  persist(
    (set, get) => ({
      user: null,
      token: null,
      isAuthenticated: false,

      login: (user, token) =>
        set({ user, token, isAuthenticated: true }),

      logout: () => {
        set({ user: null, token: null, isAuthenticated: false })
        localStorage.removeItem('jobhunt-auth')
        window.location.href = '/login'
      },

      updateUser: (updates) =>
        set((state) => ({ user: { ...state.user, ...updates } })),

      hasCompletedOnboarding: () => {
        const { user } = get()
        // Onboarding complete if user has uploaded master CV
        // We store this flag after Step 1 completes
        return Boolean(user?.onboarding_complete)
      },

      setOnboardingComplete: () =>
        set((state) => ({
          user: { ...state.user, onboarding_complete: true },
        })),
    }),
    {
      name: 'jobhunt-auth',
      partialize: (state) => ({
        user: state.user,
        token: state.token,
        isAuthenticated: state.isAuthenticated,
      }),
    }
  )
)

export default useAuthStore
