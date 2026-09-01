'use client'

import { useState, useEffect } from 'react'
import { Plus, Search, Building2, Mail, Phone, MapPin, Trash2, Edit, Eye } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger, DialogFooter } from '@/components/ui/dialog'
import { DataTable } from '@/components/data-table'
import { api, Company } from '@/lib/api'
import { useAuth } from '@/lib/auth-context'
import { toast } from 'sonner'

const initialFormData = {
  name: '',
  domain: '',
  industry: '',
  size: '',
  annual_revenue: 0,
  description: '',
  website: '',
  phone: '',
  address: '',
  city: '',
  state: '',
  country: '',
  postal_code: '',
  linkedin_url: '',
  facebook_url: '',
  twitter_url: '',
  source: '',
  custom_fields: {},
}

export default function CompaniesPage() {
  const { tenant, isLoading: authLoading } = useAuth()
  const [companies, setCompanies] = useState<Company[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [isCreating, setIsCreating] = useState(false)
  const [isEditing, setIsEditing] = useState(false)
  const [editingCompany, setEditingCompany] = useState<Company | null>(null)
  const [formData, setFormData] = useState(initialFormData)
  const [pagination, setPagination] = useState({ page: 1, pageSize: 25, total: 0, onPageChange: (page: number) => setPagination(p => ({...p, page})), onPageSizeChange: (pageSize: number) => setPagination(p => ({...p, pageSize, page: 1})) })
  const [searchQuery, setSearchQuery] = useState('')

  useEffect(() => {
    if (!authLoading && tenant) {
      fetchCompanies()
    }
  }, [authLoading, tenant, pagination.page, pagination.pageSize, searchQuery])

  const fetchCompanies = async () => {
    setIsLoading(true)
    try {
      const response = await api.listCompanies({
        page: pagination.page,
        page_size: pagination.pageSize,
      })
      setCompanies(response.items)
      setPagination((prev) => ({ ...prev, total: response.total }))
    } catch (error) {
      toast.error('Failed to load companies')
      console.error(error)
    } finally {
      setIsLoading(false)
    }
  }

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault()
    setIsCreating(true)
    try {
      const newCompany = await api.createCompany(formData)
      toast.success('Company created')
      setFormData(initialFormData)
      fetchCompanies()
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to create company')
    } finally {
      setIsCreating(false)
    }
  }

  const handleUpdate = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!editingCompany) return
    setIsEditing(true)
    try {
      await api.updateCompany(editingCompany.id, formData)
      toast.success('Company updated')
      setEditingCompany(null)
      setFormData(initialFormData)
      fetchCompanies()
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to update company')
    } finally {
      setIsEditing(false)
    }
  }

  const handleDelete = async (company: Company) => {
    if (!confirm(`Delete ${company.name}?`)) return
    try {
      await api.deleteCompany(company.id)
      toast.success('Company deleted')
      fetchCompanies()
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to delete company')
    }
  }

  const handleEdit = (company: Company) => {
    setEditingCompany(company)
    setFormData({
      name: company.name,
      domain: company.domain || '',
      industry: company.industry || '',
      size: company.size || '',
      annual_revenue: company.annual_revenue || 0,
      description: company.description || '',
      website: company.website || '',
      phone: company.phone || '',
      address: company.address || '',
      city: company.city || '',
      state: company.state || '',
      country: company.country || '',
      postal_code: company.postal_code || '',
      linkedin_url: company.linkedin_url || '',
      facebook_url: company.facebook_url || '',
      twitter_url: company.twitter_url || '',
      source: company.source || '',
      custom_fields: company.custom_fields || {},
    })
  }

  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => {
    const { name, value } = e.target
    setFormData((prev) => ({ ...prev, [name]: value }))
  }

  const columns = [
    { key: 'name', header: 'Name', sortable: true, render: (row: Company) => (
      <div>
        <p className="font-medium">{row.name}</p>
        {row.domain && <p className="text-xs text-muted-foreground">{row.domain}</p>}
      </div>
    )},
    { key: 'industry', header: 'Industry', sortable: true },
    { key: 'size', header: 'Size', sortable: true },
    { key: 'city', header: 'City', sortable: true },
    { key: 'country', header: 'Country', sortable: true },
    { key: 'website', header: 'Website', render: (row: Company) => row.website ? (
      <a href={row.website} target="_blank" rel="noopener noreferrer" className="text-primary hover:underline text-sm">
        {row.website}
      </a>
    ) : '-'},
    { key: 'phone', header: 'Phone', render: (row: Company) => row.phone || '-' },
  ]

  const actions = [
    {
      label: 'View',
      icon: <Eye className="h-4 w-4" />,
      onClick: (row: Company) => handleEdit(row),
    },
    {
      label: 'Edit',
      icon: <Edit className="h-4 w-4" />,
      onClick: (row: Company) => handleEdit(row),
    },
    {
      label: 'Delete',
      icon: <Trash2 className="h-4 w-4" />,
      onClick: handleDelete,
      variant: 'destructive' as const,
    },
  ]

  const handleSearch = (query: string) => {
    setSearchQuery(query)
    setPagination((prev) => ({ ...prev, page: 1 }))
  }

  const handlePageChange = (page: number) => {
    setPagination((prev) => ({ ...prev, page }))
  }

  const handlePageSizeChange = (pageSize: number) => {
    setPagination((prev) => ({ ...prev, pageSize, page: 1 }))
  }

  const handleSort = (key: string, order: 'asc' | 'desc') => {
    // Sorting would be handled server-side in a real app
    console.log(`Sort by ${key} ${order}`)
  }

  const openCreateDialog = () => {
    setEditingCompany(null)
    setFormData(initialFormData)
  }

  const formFields = (
    <div className="grid gap-4 sm:grid-cols-2">
      <div className="sm:col-span-2">
        <Label htmlFor="name">Name *</Label>
        <Input id="name" name="name" value={formData.name} onChange={handleChange} required placeholder="Acme Inc" />
      </div>
      <div>
        <Label htmlFor="domain">Domain</Label>
        <Input id="domain" name="domain" value={formData.domain} onChange={handleChange} placeholder="acme.com" />
      </div>
      <div>
        <Label htmlFor="industry">Industry</Label>
        <Input id="industry" name="industry" value={formData.industry} onChange={handleChange} placeholder="Technology" />
      </div>
      <div>
        <Label htmlFor="size">Size</Label>
        <Input id="size" name="size" value={formData.size} onChange={handleChange} placeholder="51-200" />
      </div>
      <div>
        <Label htmlFor="annual_revenue">Annual Revenue</Label>
        <Input id="annual_revenue" name="annual_revenue" type="number" value={formData.annual_revenue} onChange={handleChange} placeholder="1000000" />
      </div>
      <div className="sm:col-span-2">
        <Label htmlFor="website">Website</Label>
        <Input id="website" name="website" value={formData.website} onChange={handleChange} placeholder="https://acme.com" />
      </div>
      <div className="sm:col-span-2">
        <Label htmlFor="phone">Phone</Label>
        <Input id="phone" name="phone" value={formData.phone} onChange={handleChange} placeholder="+1 555-123-4567" />
      </div>
      <div className="sm:col-span-2">
        <Label htmlFor="address">Address</Label>
        <Input id="address" name="address" value={formData.address} onChange={handleChange} placeholder="123 Main St" />
      </div>
      <div>
        <Label htmlFor="city">City</Label>
        <Input id="city" name="city" value={formData.city} onChange={handleChange} placeholder="San Francisco" />
      </div>
      <div>
        <Label htmlFor="state">State</Label>
        <Input id="state" name="state" value={formData.state} onChange={handleChange} placeholder="CA" />
      </div>
      <div>
        <Label htmlFor="country">Country</Label>
        <Input id="country" name="country" value={formData.country} onChange={handleChange} placeholder="USA" />
      </div>
      <div>
        <Label htmlFor="postal_code">Postal Code</Label>
        <Input id="postal_code" name="postal_code" value={formData.postal_code} onChange={handleChange} placeholder="94105" />
      </div>
      <div className="sm:col-span-2">
        <Label htmlFor="description">Description</Label>
        <textarea
          id="description"
          name="description"
          value={formData.description}
          onChange={handleChange}
          className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
          rows={3}
          placeholder="Company description..."
        />
      </div>
    </div>
  )

  return (
    <div className="flex h-screen bg-background">
      <div className="flex-1 overflow-y-auto p-6 lg:p-8">
        <DataTable
          data={companies}
          columns={columns}
          isLoading={isLoading}
          emptyMessage="No companies found. Create your first company to get started."
          title="Companies"
          subtitle="Manage your company accounts and prospects"
          onAdd={openCreateDialog}
          actions={actions}
          pagination={pagination}
          sortBy=""
          sortOrder="asc"
          onSort={handleSort}
          searchPlaceholder="Search companies..."
          onSearch={handleSearch}
        />

        <Dialog open={!!editingCompany || isCreating} onOpenChange={(open) => { if (!open) { setEditingCompany(null); setFormData(initialFormData); } }}>
          <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
            <DialogHeader>
              <DialogTitle>{editingCompany ? 'Edit Company' : 'Create Company'}</DialogTitle>
            </DialogHeader>
            <form onSubmit={editingCompany ? handleUpdate : handleCreate}>
              {formFields}
              <DialogFooter className="gap-2">
                <Button type="button" variant="outline" onClick={() => { setEditingCompany(null); setFormData(initialFormData); }}>
                  Cancel
                </Button>
                <Button type="submit" disabled={isCreating || isEditing}>
                  {isCreating || isEditing ? 'Saving...' : editingCompany ? 'Update' : 'Create'}
                </Button>
              </DialogFooter>
            </form>
          </DialogContent>
        </Dialog>
      </div>
    </div>
  )
}