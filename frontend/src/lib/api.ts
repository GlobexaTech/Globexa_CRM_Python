// API Client for Globexa CRM
// Handles authentication, tenant context, and all API requests

import { getCookie, setCookie, deleteCookie } from 'cookies-next'

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

// ============================================
// Types - Exported for use in components
// ============================================

export interface TokenPair {
  access_token: string
  refresh_token: string
  token_type: string
  expires_in: number
}

export interface User {
  id: string
  email: string
  full_name: string
  avatar_url?: string
  phone?: string
  is_active: boolean
  is_superuser: boolean
  email_verified: boolean
  timezone: string
  locale: string
  last_login_at?: string
  created_at: string
  updated_at: string
}

export interface Tenant {
  id: string
  name: string
  slug: string
  domain?: string
  logo_url?: string
  settings: Record<string, any>
  is_active: boolean
  created_at: string
  updated_at: string
  subscription?: Subscription
  feature_entitlements?: FeatureEntitlement[]
}

export interface Subscription {
  id: string
  tenant_id: string
  package: string
  status: string
  billing_email?: string
  current_period_start?: string
  current_period_end?: string
  trial_end?: string
  created_at: string
  updated_at: string
}

export interface FeatureEntitlement {
  id: string
  tenant_id: string
  feature_key: string
  enabled: boolean
  limit_value?: number
  metadata: Record<string, any>
  created_at: string
  updated_at: string
}

// Company types
export interface Company {
  id: string
  name: string
  domain?: string
  industry?: string
  size?: string
  annual_revenue?: number
  description?: string
  website?: string
  phone?: string
  address?: string
  city?: string
  state?: string
  country?: string
  postal_code?: string
  linkedin_url?: string
  facebook_url?: string
  twitter_url?: string
  source?: string
  ai_summary?: string
  ai_icp_score?: number
  ai_icp_reason?: string
  custom_fields: Record<string, any>
  created_at: string
  updated_at: string
  created_by_id?: string
  updated_by_id?: string
}

export interface Contact {
  id: string
  company_id?: string
  first_name: string
  last_name: string
  email?: string
  phone?: string
  mobile?: string
  title?: string
  department?: string
  linkedin_url?: string
  address?: string
  city?: string
  state?: string
  country?: string
  postal_code?: string
  is_primary: boolean
  do_not_contact: boolean
  email_opted_out: boolean
  sms_opted_out: boolean
  source?: string
  ai_summary?: string
  ai_lead_score?: number
  custom_fields: Record<string, any>
  created_at: string
  updated_at: string
  created_by_id?: string
  updated_by_id?: string
  company?: Company
}

export interface Lead {
  id: string
  contact_id?: string
  company_id?: string
  title: string
  description?: string
  status: string
  owner_id?: string
  source?: string
  source_id?: string
  utm_source?: string
  utm_medium?: string
  utm_campaign?: string
  utm_content?: string
  utm_term?: string
  referrer_url?: string
  landing_page?: string
  ai_score?: number
  ai_score_reason?: string
  ai_next_action?: string
  ai_next_action_confidence?: number
  ai_summary?: string
  is_qualified: boolean
  qualified_by_id?: string
  qualified_at?: string
  qualification_notes?: string
  converted_at?: string
  converted_deal_id?: string
  custom_fields: Record<string, any>
  created_at: string
  updated_at: string
  created_by_id?: string
  updated_by_id?: string
  owner?: User
  contact?: Contact
  company?: Company
}

export interface Pipeline {
  id: string
  name: string
  description?: string
  is_default: boolean
  is_active: boolean
  created_at: string
  updated_at: string
  stages?: Stage[]
}

export interface Stage {
  id: string
  pipeline_id: string
  name: string
  order: number
  probability: number
  is_closed: boolean
  is_won: boolean
  color?: string
  created_at: string
  updated_at: string
  deals_count: number
}

export interface Deal {
  id: string
  pipeline_id: string
  stage_id: string
  contact_id?: string
  company_id?: string
  lead_id?: string
  title: string
  description?: string
  value: number
  currency: string
  owner_id?: string
  expected_close_date?: string
  probability: number
  source?: string
  actual_close_date?: string
  weighted_value: number
  custom_fields: Record<string, any>
  created_at: string
  updated_at: string
  created_by_id?: string
  updated_by_id?: string
  owner?: User
  contact?: Contact
  company?: Company
  stage?: Stage
  pipeline?: Pipeline
}

export interface PaginatedResponse<T> {
  items: T[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

export interface PaginationParams {
  page?: number
  page_size?: number
}

// ============================================
// ApiClient Class
// ============================================

class ApiClient {
  private accessToken: string | null = null
  private refreshToken: string | null = null
  private tenantId: string | null = null

  constructor() {
    if (typeof window !== 'undefined') {
      this.accessToken = getCookie('access_token') as string | null
      this.refreshToken = getCookie('refresh_token') as string | null
      this.tenantId = getCookie('tenant_id') as string | null
    }
  }

  setTokens(accessToken: string, refreshToken: string) {
    this.accessToken = accessToken
    this.refreshToken = refreshToken
    if (typeof window !== 'undefined') {
      setCookie('access_token', accessToken, { maxAge: 60 * 30, path: '/' }) // 30 min
      setCookie('refresh_token', refreshToken, { maxAge: 60 * 60 * 24 * 30, path: '/' }) // 30 days
    }
  }

  setTenantId(tenantId: string) {
    this.tenantId = tenantId
    if (typeof window !== 'undefined') {
      setCookie('tenant_id', tenantId, { maxAge: 60 * 60 * 24 * 30, path: '/' })
    }
  }

  clearAuth() {
    this.accessToken = null
    this.refreshToken = null
    this.tenantId = null
    if (typeof window !== 'undefined') {
      deleteCookie('access_token', { path: '/' })
      deleteCookie('refresh_token', { path: '/' })
      deleteCookie('tenant_id', { path: '/' })
    }
  }

  getAccessToken(): string | null {
    return this.accessToken
  }

  getTenantId(): string | null {
    return this.tenantId
  }

  isAuthenticated(): boolean {
    return !!this.accessToken
  }

  private async request<T>(
    endpoint: string,
    options: RequestInit = {}
  ): Promise<T> {
    const headers: HeadersInit = {
      'Content-Type': 'application/json',
      ...options.headers,
    }

    if (this.accessToken) {
      (headers as Record<string, string>)['Authorization'] = `Bearer ${this.accessToken}`
    }

    if (this.tenantId) {
      (headers as Record<string, string>)['X-Tenant-ID'] = this.tenantId
    }

    const response = await fetch(`${API_BASE_URL}${endpoint}`, {
      ...options,
      headers,
    })

    if (response.status === 401 && this.refreshToken) {
      const refreshed = await this.refreshAccessToken()
      if (refreshed) {
        return this.request<T>(endpoint, options)
      } else {
        this.clearAuth()
        if (typeof window !== 'undefined') {
          window.location.href = '/login'
        }
        throw new Error('Authentication expired')
      }
    }

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Request failed' }))
      throw new Error(error.detail || `HTTP ${response.status}`)
    }

    if (response.status === 204) {
      return undefined as T
    }

    return response.json()
  }

  private async refreshAccessToken(): Promise<boolean> {
    if (!this.refreshToken) return false

    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/auth/refresh`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: this.refreshToken }),
      })

      if (!response.ok) return false

      const data: TokenPair = await response.json()
      this.setTokens(data.access_token, data.refresh_token)
      return true
    } catch {
      return false
    }
  }

  // Auth endpoints
  async register(data: {
    email: string
    password: string
    full_name: string
    tenant_name?: string
    tenant_slug?: string
  }): Promise<TokenPair> {
    return this.request<TokenPair>('/api/v1/auth/register', {
      method: 'POST',
      body: JSON.stringify(data),
    })
  }

  async login(email: string, password: string): Promise<TokenPair> {
    const formData = new URLSearchParams()
    formData.append('username', email)
    formData.append('password', password)

    const response = await fetch(`${API_BASE_URL}/api/v1/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: formData.toString(),
    })

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Login failed' }))
      throw new Error(error.detail || 'Login failed')
    }

    return response.json()
  }

  async googleAuth(code: string): Promise<TokenPair> {
    return this.request<TokenPair>('/api/v1/auth/google', {
      method: 'POST',
      body: JSON.stringify({ code }),
    })
  }

  async refreshTokens(): Promise<TokenPair> {
    if (!this.refreshToken) throw new Error('No refresh token')
    return this.request<TokenPair>('/api/v1/auth/refresh', {
      method: 'POST',
      body: JSON.stringify({ refresh_token: this.refreshToken }),
    })
  }

  async getCurrentUser(): Promise<User> {
    return this.request<User>('/api/v1/auth/me')
  }

  async updateCurrentUser(data: Partial<User>): Promise<User> {
    return this.request<User>('/api/v1/auth/me', {
      method: 'PATCH',
      body: JSON.stringify(data),
    })
  }

  async switchTenant(tenantId: string): Promise<TokenPair> {
    const tokens = await this.request<TokenPair>(`/api/v1/auth/switch-tenant/${tenantId}`, {
      method: 'POST',
    })
    this.setTokens(tokens.access_token, tokens.refresh_token)
    this.setTenantId(tenantId)
    return tokens
  }

  async listUserTenants(): Promise<Array<{
    id: string
    name: string
    slug: string
    role: string
    is_default: boolean
  }>> {
    return this.request('/api/v1/auth/tenants')
  }

  // Tenant endpoints
  async createTenant(data: {
    name: string
    slug: string
    domain?: string
    logo_url?: string
    settings?: Record<string, any>
  }): Promise<Tenant> {
    return this.request<Tenant>('/api/v1/tenants', {
      method: 'POST',
      body: JSON.stringify(data),
    })
  }

  async listTenants(params?: PaginationParams): Promise<PaginatedResponse<Tenant>> {
    const searchParams = new URLSearchParams()
    if (params?.page) searchParams.set('page', params.page.toString())
    if (params?.page_size) searchParams.set('page_size', params.page_size.toString())
    return this.request<PaginatedResponse<Tenant>>(`/api/v1/tenants?${searchParams}`)
  }

  async getMyTenant(): Promise<Tenant> {
    return this.request<Tenant>('/api/v1/tenants/me')
  }

  async getTenant(tenantId: string): Promise<Tenant> {
    return this.request<Tenant>(`/api/v1/tenants/${tenantId}`)
  }

  async updateTenant(tenantId: string, data: Partial<Tenant>): Promise<Tenant> {
    return this.request<Tenant>(`/api/v1/tenants/${tenantId}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    })
  }

  async deleteTenant(tenantId: string): Promise<void> {
    return this.request<void>(`/api/v1/tenants/${tenantId}`, {
      method: 'DELETE',
    })
  }

  // Subscription endpoints
  async createSubscription(tenantId: string, data: { package: string; billing_email?: string }): Promise<Subscription> {
    return this.request<Subscription>(`/api/v1/tenants/${tenantId}/subscription`, {
      method: 'POST',
      body: JSON.stringify(data),
    })
  }

  async getSubscription(tenantId: string): Promise<Subscription> {
    return this.request<Subscription>(`/api/v1/tenants/${tenantId}/subscription`)
  }

  async updateSubscription(tenantId: string, data: Partial<Subscription>): Promise<Subscription> {
    return this.request<Subscription>(`/api/v1/tenants/${tenantId}/subscription`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    })
  }

  // Feature Entitlement endpoints
  async listEntitlements(tenantId: string): Promise<FeatureEntitlement[]> {
    return this.request<FeatureEntitlement[]>(`/api/v1/tenants/${tenantId}/entitlements`)
  }

  async createEntitlement(tenantId: string, data: Partial<FeatureEntitlement>): Promise<FeatureEntitlement> {
    return this.request<FeatureEntitlement>(`/api/v1/tenants/${tenantId}/entitlements`, {
      method: 'POST',
      body: JSON.stringify(data),
    })
  }

  async updateEntitlement(tenantId: string, featureKey: string, data: Partial<FeatureEntitlement>): Promise<FeatureEntitlement> {
    return this.request<FeatureEntitlement>(`/api/v1/tenants/${tenantId}/entitlements/${featureKey}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    })
  }

  async deleteEntitlement(tenantId: string, featureKey: string): Promise<void> {
    return this.request<void>(`/api/v1/tenants/${tenantId}/entitlements/${featureKey}`, {
      method: 'DELETE',
    })
  }

  // Pipeline endpoints
  async listPipelines(): Promise<Pipeline[]> {
    return this.request<Pipeline[]>('/api/v1/pipelines')
  }

  async getPipeline(id: string): Promise<Pipeline> {
    return this.request<Pipeline>(`/api/v1/pipelines/${id}`)
  }

  async createPipeline(data: Partial<Pipeline>): Promise<Pipeline> {
    return this.request<Pipeline>('/api/v1/pipelines', {
      method: 'POST',
      body: JSON.stringify(data),
    })
  }

  async updatePipeline(id: string, data: Partial<Pipeline>): Promise<Pipeline> {
    return this.request<Pipeline>(`/api/v1/pipelines/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    })
  }

  async deletePipeline(id: string): Promise<void> {
    return this.request<void>(`/api/v1/pipelines/${id}`, {
      method: 'DELETE',
    })
  }

  // Stage endpoints
  async listStages(pipelineId: string): Promise<Stage[]> {
    return this.request<Stage[]>(`/api/v1/pipelines/${pipelineId}/stages`)
  }

  async createStage(data: Partial<Stage>): Promise<Stage> {
    return this.request<Stage>('/api/v1/stages', {
      method: 'POST',
      body: JSON.stringify(data),
    })
  }

  async updateStage(id: string, data: Partial<Stage>): Promise<Stage> {
    return this.request<Stage>(`/api/v1/stages/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    })
  }

  async deleteStage(id: string): Promise<void> {
    return this.request<void>(`/api/v1/stages/${id}`, {
      method: 'DELETE',
    })
  }

  // Company endpoints
  async listCompanies(params?: PaginationParams): Promise<PaginatedResponse<Company>> {
    const searchParams = new URLSearchParams()
    if (params?.page) searchParams.set('page', params.page.toString())
    if (params?.page_size) searchParams.set('page_size', params.page_size.toString())
    return this.request<PaginatedResponse<Company>>(`/api/v1/companies?${searchParams}`)
  }

  async getCompany(id: string): Promise<Company> {
    return this.request<Company>(`/api/v1/companies/${id}`)
  }

  async createCompany(data: Partial<Company>): Promise<Company> {
    return this.request<Company>('/api/v1/companies', {
      method: 'POST',
      body: JSON.stringify(data),
    })
  }

  async updateCompany(id: string, data: Partial<Company>): Promise<Company> {
    return this.request<Company>(`/api/v1/companies/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    })
  }

  async deleteCompany(id: string): Promise<void> {
    return this.request<void>(`/api/v1/companies/${id}`, {
      method: 'DELETE',
    })
  }

  // Contact endpoints
  async listContacts(params?: PaginationParams): Promise<PaginatedResponse<Contact>> {
    const searchParams = new URLSearchParams()
    if (params?.page) searchParams.set('page', params.page.toString())
    if (params?.page_size) searchParams.set('page_size', params.page_size.toString())
    return this.request<PaginatedResponse<Contact>>(`/api/v1/contacts?${searchParams}`)
  }

  async getContact(id: string): Promise<Contact> {
    return this.request<Contact>(`/api/v1/contacts/${id}`)
  }

  async createContact(data: Partial<Contact>): Promise<Contact> {
    return this.request<Contact>('/api/v1/contacts', {
      method: 'POST',
      body: JSON.stringify(data),
    })
  }

  async updateContact(id: string, data: Partial<Contact>): Promise<Contact> {
    return this.request<Contact>(`/api/v1/contacts/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    })
  }

  async deleteContact(id: string): Promise<void> {
    return this.request<void>(`/api/v1/contacts/${id}`, {
      method: 'DELETE',
    })
  }

  // Lead endpoints
  async listLeads(params?: PaginationParams): Promise<PaginatedResponse<Lead>> {
    const searchParams = new URLSearchParams()
    if (params?.page) searchParams.set('page', params.page.toString())
    if (params?.page_size) searchParams.set('page_size', params.page_size.toString())
    return this.request<PaginatedResponse<Lead>>(`/api/v1/leads?${searchParams}`)
  }

  async getLead(id: string): Promise<Lead> {
    return this.request<Lead>(`/api/v1/leads/${id}`)
  }

  async createLead(data: Partial<Lead>): Promise<Lead> {
    return this.request<Lead>('/api/v1/leads', {
      method: 'POST',
      body: JSON.stringify(data),
    })
  }

  async updateLead(id: string, data: Partial<Lead>): Promise<Lead> {
    return this.request<Lead>(`/api/v1/leads/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    })
  }

  async deleteLead(id: string): Promise<void> {
    return this.request<void>(`/api/v1/leads/${id}`, {
      method: 'DELETE',
    })
  }

  // Deal endpoints
  async listDeals(params?: PaginationParams): Promise<PaginatedResponse<Deal>> {
    const searchParams = new URLSearchParams()
    if (params?.page) searchParams.set('page', params.page.toString())
    if (params?.page_size) searchParams.set('page_size', params.page_size.toString())
    return this.request<PaginatedResponse<Deal>>(`/api/v1/deals?${searchParams}`)
  }

  async getDeal(id: string): Promise<Deal> {
    return this.request<Deal>(`/api/v1/deals/${id}`)
  }

  async createDeal(data: Partial<Deal>): Promise<Deal> {
    return this.request<Deal>('/api/v1/deals', {
      method: 'POST',
      body: JSON.stringify(data),
    })
  }

  async updateDeal(id: string, data: Partial<Deal>): Promise<Deal> {
    return this.request<Deal>(`/api/v1/deals/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    })
  }

  async deleteDeal(id: string): Promise<void> {
    return this.request<void>(`/api/v1/deals/${id}`, {
      method: 'DELETE',
    })
  }

  // Health check
  async healthCheck(): Promise<{ status: string }> {
    return this.request<{ status: string }>('/health')
  }
}

// Singleton instance
export const api = new ApiClient()

// React hook for API
export function useApi() {
  return api
}