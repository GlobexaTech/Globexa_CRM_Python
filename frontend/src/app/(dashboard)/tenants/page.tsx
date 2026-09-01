'use client'

import { useState, useEffect } from 'react'
import { Plus, Search, Building2, Trash2, Edit, Eye, Key, Shield, Users, CreditCard, Settings } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { DataTable } from '@/components/data-table'
import { api, Tenant, Subscription, FeatureEntitlement } from '@/lib/api'
import { useAuth } from '@/lib/auth-context'
import { toast } from 'sonner'
import { Badge } from '@/components/ui/badge'

const initialTenantData = {
  name: '',
  slug: '',
  domain: '',
  logo_url: '',
  settings: {},
}

const initialSubscriptionData = {
  package: 'starter',
  billing_email: '',
}

const initialEntitlementData = {
  feature_key: '',
  enabled: true,
  limit_value: '',
  metadata: {},
}

export default function TenantsPage() {
  const { tenant: currentTenant, isLoading: authLoading, isAuthenticated, user } = useAuth()
  const [tenants, setTenants] = useState<Tenant[]>([])
  const [selectedTenant, setSelectedTenant] = useState<Tenant | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [isCreating, setIsCreating] = useState(false)
  const [isEditing, setIsEditing] = useState(false)
  const [activeTab, setActiveTab] = useState<'list' | 'details' | 'subscription' | 'entitlements'>('list')
  const [pagination, setPagination] = useState({ page: 1, pageSize: 25, total: 0, onPageChange: (page: number) => setPagination(p => ({...p, page})), onPageSizeChange: (pageSize: number) => setPagination(p => ({...p, pageSize, page: 1})) })
  const [searchQuery, setSearchQuery] = useState('')
  const [tenantFormData, setTenantFormData] = useState(initialTenantData)
  const [subscriptionFormData, setSubscriptionFormData] = useState(initialSubscriptionData)
  const [entitlements, setEntitlements] = useState<FeatureEntitlement[]>([])
  const [newEntitlement, setNewEntitlement] = useState(initialEntitlementData)

  useEffect(() => {
    if (!authLoading && isAuthenticated) {
      fetchTenants()
    }
  }, [authLoading, isAuthenticated, pagination.page, pagination.pageSize, searchQuery])

  const fetchTenants = async () => {
    setIsLoading(true)
    try {
      const response = await api.listTenants({
        page: pagination.page,
        page_size: pagination.pageSize,
      })
      setTenants(response.items)
      setPagination((prev) => ({ ...prev, total: response.total }))
    } catch (error) {
      toast.error('Failed to load tenants')
      console.error(error)
    } finally {
      setIsLoading(false)
    }
  }

  const fetchTenantDetails = async (tenantId: string) => {
    try {
      const [tenantData, entitlementsData] = await Promise.all([
        api.getTenant(tenantId),
        api.listEntitlements(tenantId),
      ])
      setSelectedTenant(tenantData)
      setEntitlements(entitlementsData)
      setActiveTab('details')
    } catch (error) {
      toast.error('Failed to load tenant details')
      console.error(error)
    }
  }

  const handleCreateTenant = async (e: React.FormEvent) => {
    e.preventDefault()
    setIsCreating(true)
    try {
      await api.createTenant(tenantFormData)
      toast.success('Tenant created')
      setTenantFormData(initialTenantData)
      fetchTenants()
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to create tenant')
    } finally {
      setIsCreating(false)
    }
  }

  const handleUpdateTenant = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!selectedTenant) return
    setIsEditing(true)
    try {
      await api.updateTenant(selectedTenant.id, tenantFormData)
      toast.success('Tenant updated')
      setEditingTenant(null)
      setTenantFormData(initialTenantData)
      fetchTenants()
      fetchTenantDetails(selectedTenant.id)
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to update tenant')
    } finally {
      setIsEditing(false)
    }
  }

  const handleDeleteTenant = async (tenant: Tenant) => {
    if (!confirm(`Delete tenant "${tenant.name}"? This action cannot be undone.`)) return
    try {
      await api.deleteTenant(tenant.id)
      toast.success('Tenant deleted')
      fetchTenants()
      if (selectedTenant?.id === tenant.id) {
        setSelectedTenant(null)
      }
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to delete tenant')
    }
  }

  const handleEditTenant = (tenant: Tenant) => {
    setEditingTenant(tenant)
    setTenantFormData({
      name: tenant.name,
      slug: tenant.slug,
      domain: tenant.domain || '',
      logo_url: tenant.logo_url || '',
      settings: tenant.settings || {},
    })
  }

  const [editingTenant, setEditingTenant] = useState<Tenant | null>(null)

  const tenantColumns = [
    { key: 'name', header: 'Name', sortable: true, render: (row: Tenant) => (
      <div>
        <p className="font-medium">{row.name}</p>
        <p className="text-xs text-muted-foreground">{row.slug}</p>
      </div>
    )},
    { key: 'domain', header: 'Domain', sortable: true, render: (row: Tenant) => row.domain || '-' },
    { key: 'is_active', header: 'Status', render: (row: Tenant) => (
      <Badge variant={row.is_active ? 'default' : 'secondary'}>
        {row.is_active ? 'Active' : 'Inactive'}
      </Badge>
    )},
    { key: 'subscription', header: 'Package', render: (row: Tenant) => row.subscription ? (
      <Badge variant="default">{row.subscription.package}</Badge>
    ) : (
      <Badge variant="secondary">None</Badge>
    )},
  ]

  const tenantActions = [
    { label: 'View Details', icon: <Eye className="h-4 w-4" />, onClick: (row: Tenant) => fetchTenantDetails(row.id) },
    { label: 'Edit', icon: <Edit className="h-4 w-4" />, onClick: handleEditTenant },
    { label: 'Delete', icon: <Trash2 className="h-4 w-4" />, onClick: handleDeleteTenant, variant: 'destructive' as const },
  ]

  const handleSearch = (query: string) => { setSearchQuery(query); setPagination((prev) => ({ ...prev, page: 1 })) }
  const handlePageChange = (page: number) => setPagination((prev) => ({ ...prev, page }))
  const handlePageSizeChange = (pageSize: number) => setPagination((prev) => ({ ...prev, pageSize, page: 1 }))

  if (!isAuthenticated) {
    return (
      <div className="flex h-screen items-center justify-center">
        <div className="text-center">
          <Building2 className="h-12 w-12 mx-auto mb-4 text-muted-foreground" />
          <h2 className="text-xl font-semibold">Please sign in to view tenants</h2>
        </div>
      </div>
    )
  }

  return (
    <div className="flex h-screen bg-background">
      <div className="flex-1 overflow-y-auto p-6 lg:p-8">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 mb-6">
          <div>
            <h1 className="text-3xl font-bold tracking-tight">Tenants</h1>
            <p className="text-muted-foreground mt-1">Manage tenant accounts and subscriptions</p>
          </div>
          <Button onClick={() => { setEditingTenant(null); setTenantFormData(initialTenantData); }}>
            <Plus className="mr-2 h-4 w-4" />
            Add Tenant
          </Button>
        </div>

        {/* Tenants List */}
        <Card className="mb-8">
          <CardHeader>
            <CardTitle>All Tenants</CardTitle>
          </CardHeader>
          <CardContent>
            <DataTable
              data={tenants}
              columns={tenantColumns}
              isLoading={isLoading}
              emptyMessage="No tenants found."
              actions={tenantActions}
              pagination={pagination}
              sortBy=""
              sortOrder="asc"
              onSort={() => {}}
              searchPlaceholder="Search tenants..."
              onSearch={handleSearch}
            />
          </CardContent>
        </Card>

        {/* Tenant Details */}
        {selectedTenant && (
          <Tabs value={activeTab} onValueChange={(value: string) => setActiveTab(value as 'list' | 'details' | 'subscription' | 'entitlements')} className="space-y-4">
            <TabsList>
              <TabsTrigger value="details" onClick={() => fetchTenantDetails(selectedTenant.id)}>
                <Settings className="mr-2 h-4 w-4" />
                Details
              </TabsTrigger>
              <TabsTrigger value="subscription">
                <CreditCard className="mr-2 h-4 w-4" />
                Subscription
              </TabsTrigger>
              <TabsTrigger value="entitlements">
                <Shield className="mr-2 h-4 w-4" />
                Entitlements
              </TabsTrigger>
            </TabsList>

            <TabsContent value="details">
              <Card>
                <CardHeader>
                  <CardTitle>{selectedTenant.name}</CardTitle>
                </CardHeader>
                <CardContent className="grid gap-4 sm:grid-cols-2">
                  <div>
                    <Label>ID</Label>
                    <p className="font-mono text-sm">{selectedTenant.id}</p>
                  </div>
                  <div>
                    <Label>Slug</Label>
                    <p>{selectedTenant.slug}</p>
                  </div>
                  <div>
                    <Label>Domain</Label>
                    <p>{selectedTenant.domain || 'Not configured'}</p>
                  </div>
                  <div>
                    <Label>Status</Label>
                    <Badge variant={selectedTenant.is_active ? 'default' : 'secondary'}>
                      {selectedTenant.is_active ? 'Active' : 'Inactive'}
                    </Badge>
                  </div>
                  <div className="sm:col-span-2">
                    <Label>Settings</Label>
                    <pre className="text-sm text-muted-foreground bg-muted p-4 rounded">{JSON.stringify(selectedTenant.settings, null, 2)}</pre>
                  </div>
                </CardContent>
              </Card>
            </TabsContent>

            <TabsContent value="subscription">
              <Card>
                <CardHeader>
                  <CardTitle>Subscription</CardTitle>
                </CardHeader>
                <CardContent>
                  {selectedTenant.subscription ? (
                    <div className="grid gap-4 sm:grid-cols-2">
                      <div>
                        <Label>Package</Label>
                        <Badge variant="default">{selectedTenant.subscription.package}</Badge>
                      </div>
                      <div>
                        <Label>Status</Label>
                        <Badge variant={selectedTenant.subscription.status === 'active' ? 'default' : 'secondary'}>
                          {selectedTenant.subscription.status}
                        </Badge>
                      </div>
                      <div>
                        <Label>Billing Email</Label>
                        <p>{selectedTenant.subscription.billing_email || 'Not set'}</p>
                      </div>
                      <div>
                        <Label>Current Period End</Label>
                        <p>{selectedTenant.subscription.current_period_end ? new Date(selectedTenant.subscription.current_period_end).toLocaleDateString() : 'Not set'}</p>
                      </div>
                      <div>
                        <Label>Trial Ends</Label>
                        <p>{selectedTenant.subscription.trial_end ? new Date(selectedTenant.subscription.trial_end).toLocaleDateString() : 'Not set'}</p>
                      </div>
                    </div>
                  ) : (
                    <div className="text-center py-8">
                      <CreditCard className="h-12 w-12 mx-auto mb-4 text-muted-foreground" />
                      <p className="text-muted-foreground">No subscription configured</p>
                      <Button onClick={() => setActiveTab('subscription')} className="mt-4">
                        Create Subscription
                      </Button>
                    </div>
                  )}
                </CardContent>
              </Card>
            </TabsContent>

            <TabsContent value="entitlements">
              <Card>
                <CardHeader className="flex flex-row items-center justify-between">
                  <CardTitle>Feature Entitlements</CardTitle>
                  <Button size="sm" onClick={() => { setNewEntitlement(initialEntitlementData); /* open dialog */ }}>
                    <Plus className="mr-2 h-4 w-4" />
                    Add Entitlement
                  </Button>
                </CardHeader>
                <CardContent>
                  {entitlements.length === 0 ? (
                    <div className="text-center py-8">
                      <Shield className="h-12 w-12 mx-auto mb-4 text-muted-foreground" />
                      <p className="text-muted-foreground">No entitlements configured</p>
                    </div>
                  ) : (
                    <div className="space-y-3">
                      {entitlements.map((ent) => (
                        <div key={ent.id} className="flex items-center justify-between p-4 border rounded-lg">
                          <div>
                            <p className="font-medium">{ent.feature_key}</p>
                            <p className="text-sm text-muted-foreground">Limit: {ent.limit_value || 'Unlimited'}</p>
                          </div>
                          <Badge variant={ent.enabled ? 'default' : 'secondary'}>
                            {ent.enabled ? 'Enabled' : 'Disabled'}
                          </Badge>
                        </div>
                      ))}
                    </div>
                  )}
                </CardContent>
              </Card>
            </TabsContent>
          </Tabs>
        )}

        {/* Create/Edit Tenant Dialog */}
        <Dialog open={!!editingTenant || isCreating} onOpenChange={(open) => { if (!open) { setEditingTenant(null); setTenantFormData(initialTenantData); } }}>
          <DialogContent className="max-w-md">
            <DialogHeader>
              <DialogTitle>{editingTenant ? 'Edit Tenant' : 'Create Tenant'}</DialogTitle>
            </DialogHeader>
            <form onSubmit={editingTenant ? handleUpdateTenant : handleCreateTenant}>
              <div className="grid gap-4 py-4">
                <div>
                  <Label htmlFor="name">Name *</Label>
                  <Input id="name" name="name" value={tenantFormData.name} onChange={(e) => setTenantFormData({...tenantFormData, name: e.target.value})} required placeholder="Acme Inc" />
                </div>
                <div>
                  <Label htmlFor="slug">Slug *</Label>
                  <Input id="slug" name="slug" value={tenantFormData.slug} onChange={(e) => setTenantFormData({...tenantFormData, slug: e.target.value})} required placeholder="acme-inc" />
                </div>
                <div>
                  <Label htmlFor="domain">Domain</Label>
                  <Input id="domain" name="domain" value={tenantFormData.domain} onChange={(e) => setTenantFormData({...tenantFormData, domain: e.target.value})} placeholder="acme.com" />
                </div>
              </div>
              <DialogFooter className="gap-2">
                <Button type="button" variant="outline" onClick={() => { setEditingTenant(null); setTenantFormData(initialTenantData); }}>
                  Cancel
                </Button>
                <Button type="submit" disabled={isCreating || isEditing}>
                  {isCreating || isEditing ? 'Saving...' : editingTenant ? 'Update' : 'Create'}
                </Button>
              </DialogFooter>
            </form>
          </DialogContent>
        </Dialog>
      </div>
    </div>
  )
}