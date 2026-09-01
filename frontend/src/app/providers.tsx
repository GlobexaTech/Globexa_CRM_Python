'use client'

import { ReactNode } from 'react'
import { AuthProvider } from '@/lib/auth-context'
import { Toaster } from '@/components/ui/sonner'

export function Providers({ children }: { children: ReactNode }) {
  return (
    <AuthProvider>
      {children}
      <Toaster position="top-right" />
    </AuthProvider>
  )
}