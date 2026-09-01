'use client'

import { useState, useEffect } from 'react'
import { Plus, Search, Users, Mail, Phone, Building2, Trash2, Edit, Eye } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog'
import { DataTable } from '@/components/data-table'
import { api, Contact, Company } from '@/lib/api'
import { useAuth } from '@/lib/auth-context'
import { toast } from 'sonner'

const initialFormData = {
  company_id: '',
  first_name: '',
  last_name: '',
  email: '',
  phone: '',
  mobile: '',
  title: '',
  department: '',
  linkedin_url: '',
  address: '',
  city: '',
  state: '',
  country: '',
  postal_code: '',
  is_primary: false,
  do_not_contact: false,
  email_opted_out: false,
  sms_opted_out: false,
  source: '',
  custom_fields: {},
}

export default function ContactsPage() {
  const { tenant, isLoading: authLoading } = useAuth()
  const [contacts, setContacts] = useState<Contact[]>([])
  const [companies, setCompanies] = useState<Company[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [isCreating, setIsCreating] = useState(false)
  const [isEditing, setIsEditing] = useState(false)
  const [editingContact, setEditingContact] = useState<Contact | null>(null)
  const [formData, setFormData] = useState(initialFormData)
  const [pagination, setPagination] = useState({ page: 1, pageSize: 25, total: 0, onPageChange: (page: number) => setPagination(p => ({...p, page})), onPageSizeChange: (pageSize: number) => setPagination(p => ({...p, pageSize, page: 1})) })
  const [searchQuery, setSearchQuery] = useState('')

  useEffect(() => {
    if (!authLoading && tenant) {
      fetchContacts()
      fetchCompanies()
    }
  }, [authLoading, tenant, pagination.page, pagination.pageSize, searchQuery])

  const fetchContacts = async () => {
    setIsLoading(true)
    try {
      const response = await api.listContacts({
        page: pagination.page,
        page_size: pagination.pageSize,
      })
      setContacts(response.items)
      setPagination((prev) => ({ ...prev, total: response.total }))
    } catch (error) {
      toast.error('Failed to load contacts')
      console.error(error)
    } finally {
      setIsLoading(false)
    }
  }

  const fetchCompanies = async () => {
    try {
      const response = await api.listCompanies({ page_size: 100 })
      setCompanies(response.items)
    } catch (error) {
      console.error('Failed to load companies for dropdown:', error)
    }
  }

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault()
    setIsCreating(true)
    try {
      const payload = { ...formData, company_id: formData.company_id || undefined }
      await api.createContact(payload)
      toast.success('Contact created')
      setFormData(initialFormData)
      fetchContacts()
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to create contact')
    } finally {
      setIsCreating(false)
    }
  }

  const handleUpdate = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!editingContact) return
    setIsEditing(true)
    try {
      const payload = { ...formData, company_id: formData.company_id || undefined }
      await api.updateContact(editingContact.id, payload)
      toast.success('Contact updated')
      setEditingContact(null)
      setFormData(initialFormData)
      fetchContacts()
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to update contact')
    } finally {
      setIsEditing(false)
    }
  }

  const handleDelete = async (contact: Contact) => {
    if (!confirm(`Delete ${contact.first_name} ${contact.last_name}?`)) return
    try {
      await api.deleteContact(contact.id)
      toast.success('Contact deleted')
      fetchContacts()
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to delete contact')
    }
  }

  const handleEdit = (contact: Contact) => {
    setEditingContact(contact)
    setFormData({
      company_id: contact.company_id || '',
      first_name: contact.first_name,
      last_name: contact.last_name,
      email: contact.email || '',
      phone: contact.phone || '',
      mobile: contact.mobile || '',
      title: contact.title || '',
      department: contact.department || '',
      linkedin_url: contact.linkedin_url || '',
      address: contact.address || '',
      city: contact.city || '',
      state: contact.state || '',
      country: contact.country || '',
      postal_code: contact.postal_code || '',
      is_primary: contact.is_primary,
      do_not_contact: contact.do_not_contact,
      email_opted_out: contact.email_opted_out,
      sms_opted_out: contact.sms_opted_out,
      source: contact.source || '',
      custom_fields: contact.custom_fields || {},
    })
  }

  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => {
    const { name, value, type } = e.target
    setFormData((prev) => ({ ...prev, [name]: type === 'checkbox' ? (e.target as HTMLInputElement).checked : value }))
  }

  const columns = [
    { key: 'full_name', header: 'Name', sortable: true, render: (row: Contact) => (
      <div>
        <p className="font-medium">{row.first_name} {row.last_name}</p>
        {row.company && <p className="text-xs text-muted-foreground">{row.company.name}</p>}
      </div>
    )},
    { key: 'email', header: 'Email', sortable: true, render: (row: Contact) => row.email ? (
      <a href={`mailto:${row.email}`} className="text-primary hover:underline">{row.email}</a>
    ) : '-'},
    { key: 'phone', header: 'Phone', render: (row: Contact) => row.phone || row.mobile || '-' },
    { key: 'title', header: 'Title', sortable: true },
    { key: 'city', header: 'City', sortable: true },
    { key: 'country', header: 'Country', sortable: true },
  ]

  const actions = [
    { label: 'View', icon: <Eye className="h-4 w-4" />, onClick: (row: Contact) => handleEdit(row) },
    { label: 'Edit', icon: <Edit className="h-4 w-4" />, onClick: (row: Contact) => handleEdit(row) },
    { label: 'Delete', icon: <Trash2 className="h-4 w-4" />, onClick: handleDelete, variant: 'destructive' as const },
  ]

  const handleSearch = (query: string) => {
    setSearchQuery(query)
    setPagination((prev) => ({ ...prev, page: 1 }))
  }

  const handlePageChange = (page: number) => setPagination((prev) => ({ ...prev, page }))
  const handlePageSizeChange = (pageSize: number) => setPagination((prev) => ({ ...prev, pageSize, page: 1 }))
  const handleSort = (key: string, order: 'asc' | 'desc') => console.log(`Sort by ${key} ${order}`)

  const openCreateDialog = () => { setEditingContact(null); setFormData(initialFormData) }

  const formFields = (
    <div className="grid gap-4 sm:grid-cols-2">
      <div className="sm:col-span-2">
        <Label htmlFor="first_name">First Name *</Label>
        <Input id="first_name" name="first_name" value={formData.first_name} onChange={handleChange} required placeholder="John" />
      </div>
      <div>
        <Label htmlFor="last_name">Last Name *</Label>
        <Input id="last_name" name="last_name" value={formData.last_name} onChange={handleChange} required placeholder="Doe" />
      </div>
      <div>
        <Label htmlFor="company_id">Company</Label>
        <select id="company_id" name="company_id" value={formData.company_id} onChange={handleChange} className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm">
          <option value="">Select company...</option>
          {companies.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
        </select>
      </div>
      <div>
        <Label htmlFor="email">Email</Label>
        <Input id="email" name="email" type="email" value={formData.email} onChange={handleChange} placeholder="john@company.com" />
      </div>
      <div>
        <Label htmlFor="phone">Phone</Label>
        <Input id="phone" name="phone" value={formData.phone} onChange={handleChange} placeholder="+1 555-123-4567" />
      </div>
      <div>
        <Label htmlFor="mobile">Mobile</Label>
        <Input id="mobile" name="mobile" value={formData.mobile} onChange={handleChange} placeholder="+1 555-987-6543" />
      </div>
      <div>
        <Label htmlFor="title">Title</Label>
        <Input id="title" name="title" value={formData.title} onChange={handleChange} placeholder="VP of Sales" />
      </div>
      <div>
        <Label htmlFor="department">Department</Label>
        <Input id="department" name="department" value={formData.department} onChange={handleChange} placeholder="Sales" />
      </div>
      <div className="sm:col-span-2">
        <Label htmlFor="linkedin_url">LinkedIn</Label>
        <Input id="linkedin_url" name="linkedin_url" value={formData.linkedin_url} onChange={handleChange} placeholder="https://linkedin.com/in/johndoe" />
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
      <div className="sm:col-span-2 flex items-center gap-4">
        <label className="flex items-center gap-2 cursor-pointer">
          <input type="checkbox" name="is_primary" checked={formData.is_primary} onChange={handleChange} className="h-4 w-4 rounded border-input" />
          <span className="text-sm">Primary Contact</span>
        </label>
        <label className="flex items-center gap-2 cursor-pointer">
          <input type="checkbox" name="do_not_contact" checked={formData.do_not_contact} onChange={handleChange} className="h-4 w-4 rounded border-input" />
          <span className="text-sm">Do Not Contact</span>
        </label>
        <label className="flex items-center gap-2 cursor-pointer">
          <input type="checkbox" name="email_opted_out" checked={formData.email_opted_out} onChange={handleChange} className="h-4 w-4 rounded border-input" />
          <span className="text-sm">Email Opted Out</span>
        </label>
        <label className="flex items-center gap-2 cursor-pointer">
          <input type="checkbox" name="sms_opted_out" checked={formData.sms_opted_out} onChange={handleChange} className="h-4 w-4 rounded border-input" />
          <span className="text-sm">SMS Opted Out</span>
        </label>
      </div>
    </div>
  )

  return (
    <div className="flex h-screen bg-background">
      <div className="flex-1 overflow-y-auto p-6 lg:p-8">
        <DataTable
          data={contacts}
          columns={columns}
          isLoading={isLoading}
          emptyMessage="No contacts found. Create your first contact to get started."
          title="Contacts"
          subtitle="Manage your contacts and relationships"
          onAdd={openCreateDialog}
          actions={actions}
          pagination={pagination}
          sortBy=""
          sortOrder="asc"
          onSort={handleSort}
          searchPlaceholder="Search contacts..."
          onSearch={handleSearch}
        />

        <Dialog open={!!editingContact || isCreating} onOpenChange={(open) => { if (!open) { setEditingContact(null); setFormData(initialFormData); } }}>
          <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
            <DialogHeader>
              <DialogTitle>{editingContact ? 'Edit Contact' : 'Create Contact'}</DialogTitle>
            </DialogHeader>
            <form onSubmit={editingContact ? handleUpdate : handleCreate}>
              {formFields}
              <DialogFooter className="gap-2">
                <Button type="button" variant="outline" onClick={() => { setEditingContact(null); setFormData(initialFormData); }}>
                  Cancel
                </Button>
                <Button type="submit" disabled={isCreating || isEditing}>
                  {isCreating || isEditing ? 'Saving...' : editingContact ? 'Update' : 'Create'}
                </Button>
              </DialogFooter>
            </form>
          </DialogContent>
        </Dialog>
      </div>
    </div>
  )
}