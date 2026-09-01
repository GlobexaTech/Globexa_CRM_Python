// Auth Context for Globexa CRM
// Provides authentication state and methods across the app

'use client'

import React, { createContext, useContext, useState, useEffect, useCallback, ReactNode } from 'react'
import { api, User, Tenant } from '@/lib/api'
import { useRouter, usePathname } from 'next/navigation'
import { Toaster } from '@/components/ui/sonner'

interface AuthContextType {
  user: User | null
  tenant: Tenant | null
  tenants: Array<{ id: string; name: string; slug: string; role: string; is_default: boolean }>
  isLoading: boolean
  isAuthenticated: boolean
  login: (email: string, password: string) => Promise<void>
  register: (data: { email: string; password: string; full_name: string; tenant_name?: string; tenant_slug?: string }) => Promise<void>
  logout: () => void
  switchTenant: (tenantId: string) => Promise<void>
  refreshUser: () => Promise<void>
  refreshTenant: () => Promise<void>
}

const AuthContext = createContext<AuthContextType | undefined>(undefined)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [tenant, setTenant] = useState<Tenant | null>(null)
  const [tenants, setTenants] = useState<Array<{ id: string; name: string; slug: string; role: string; is_default: boolean }>>([])
  const [isLoading, setIsLoading] = useState(true)
  const router = useRouter()
  const pathname = usePathname()

  const refreshUser = useCallback(async () => {
    if (!api.isAuthenticated()) return
    try {
      const userData = await api.getCurrentUser()
      setUser(userData)
    } catch {
      setUser(null)
    }
  }, [])

  const refreshTenant = useCallback(async () => {
    if (!api.isAuthenticated() || !api.getTenantId()) return
    try {
      const tenantData = await api.getMyTenant()
      setTenant(tenantData)
    } catch {
      setTenant(null)
    }
  }, [])

  const refreshTenants = useCallback(async () => {
    if (!api.isAuthenticated()) return
    try {
      const tenantsData = await api.listUserTenants()
      setTenants(tenantsData)
    } catch {
      setTenants([])
    }
  }, [])

  const initializeAuth = useCallback(async () => {
    if (!api.isAuthenticated()) {
      setIsLoading(false)
      return
    }

    setIsLoading(true)
    try {
      await Promise.all([refreshUser(), refreshTenant(), refreshTenants()])
    } finally {
      setIsLoading(false)
    }
  }, [refreshUser, refreshTenant, refreshTenants])

  useEffect(() => {
    initializeAuth()
  }, [initializeAuth])

  // Re-initialize on tenant change
  useEffect(() => {
    if (api.getTenantId()) {
      refreshTenant()
    }
  }, [api.getTenantId(), refreshTenant])

  const login = async (email: string, password: string) => {
    const tokens = await api.login(email, password)
    api.setTokens(tokens.access_token, tokens.refresh_token)
    await initializeAuth()
    router.push('/dashboard')
    router.refresh()
  }

  const register = async (data: { email: string; password: string; full_name: string; tenant_name?: string; tenant_slug?: string }) => {
    const tokens = await api.register(data)
    api.setTokens(tokens.access_token, tokens.refresh_token)
    await initializeAuth()
    router.push('/dashboard')
    router.refresh()
  }

  const logout = () => {
    api.clearAuth()
    setUser(null)
    setTenant(null)
    setTenants([])
    router.push('/login')
    router.refresh()
  }

  const switchTenant = async (tenantId: string) => {
    await api.switchTenant(tenantId)
    await refreshTenant()
    router.refresh()
  }

  return (
    <AuthContext.Provider
      value={{
        user,
        tenant,
        tenants,
        isLoading,
        isAuthenticated: !!user,
        login,
        register,
        logout,
        switchTenant,
        refreshUser,
        refreshTenant,
      }}
    >
      {children}
      <Toaster position="top-right" />
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider')
  }
  return context
}