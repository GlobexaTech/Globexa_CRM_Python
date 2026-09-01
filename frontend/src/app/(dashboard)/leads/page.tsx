'use client'

import { useState, useEffect } from 'react'
import { Plus, Search, Target, Trash2, Edit, Eye, ArrowRight, ArrowLeft, ChevronLeft, ChevronRight } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { DataTable } from '@/components/data-table'
import { api, Lead, Company, Contact } from '@/lib/api'
import { useAuth } from '@/lib/auth-context'
import { toast } from 'sonner'
import { Badge } from '@/components/ui/badge'

const leadStatuses = ['new', 'contacted', 'qualified', 'proposal', 'negotiation', 'closed_won', 'closed_lost']
const initialFormData = {
  contact_id: '',
  company_id: '',
  title: '',
  description: '',
  status: 'new',
  owner_id: '',
  source: '',
  source_id: '',
  utm_source: '',
  utm_medium: '',
  utm_campaign: '',
  utm_content: '',
  utm_term: '',
  referrer_url: '',
  landing_page: '',
  custom_fields: {},
}

export default function LeadsPage() {
  const { tenant, isLoading: authLoading } = useAuth()
  const [leads, setLeads] = useState<Lead[]>([])
  const [companies, setCompanies] = useState<Company[]>([])
  const [contacts, setContacts] = useState<Contact[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [isCreating, setIsCreating] = useState(false)
  const [isEditing, setIsEditing] = useState(false)
  const [editingLead, setEditingLead] = useState<Lead | null>(null)
  const [formData, setFormData] = useState(initialFormData)
  const [pagination, setPagination] = useState({ page: 1, pageSize: 25, total: 0, onPageChange: (page: number) => setPagination(p => ({...p, page})), onPageSizeChange: (pageSize: number) => setPagination(p => ({...p, pageSize, page: 1})) })
  const [searchQuery, setSearchQuery] = useState('')

  useEffect(() => {
    if (!authLoading && tenant) {
      fetchLeads()
      fetchCompanies()
      fetchContacts()
    }
  }, [authLoading, tenant, pagination.page, pagination.pageSize, searchQuery])

  const fetchLeads = async () => {
    setIsLoading(true)
    try {
      const response = await api.listLeads({
        page: pagination.page,
        page_size: pagination.pageSize,
      })
      setLeads(response.items)
      setPagination((prev) => ({ ...prev, total: response.total }))
    } catch (error) {
      toast.error('Failed to load leads')
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
      console.error('Failed to load companies:', error)
    }
  }

  const fetchContacts = async () => {
    try {
      const response = await api.listContacts({ page_size: 100 })
      setContacts(response.items)
    } catch (error) {
      console.error('Failed to load contacts:', error)
    }
  }

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault()
    setIsCreating(true)
    try {
      const payload = { ...formData, contact_id: formData.contact_id || undefined, company_id: formData.company_id || undefined }
      await api.createLead(payload)
      toast.success('Lead created')
      setFormData(initialFormData)
      fetchLeads()
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to create lead')
    } finally {
      setIsCreating(false)
    }
  }

  const handleUpdate = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!editingLead) return
    setIsEditing(true)
    try {
      const payload = { ...formData, contact_id: formData.contact_id || undefined, company_id: formData.company_id || undefined }
      await api.updateLead(editingLead.id, payload)
      toast.success('Lead updated')
      setEditingLead(null)
      setFormData(initialFormData)
      fetchLeads()
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to update lead')
    } finally {
      setIsEditing(false)
    }
  }

  const handleDelete = async (lead: Lead) => {
    if (!confirm(`Delete ${lead.title}?`)) return
    try {
      await api.deleteLead(lead.id)
      toast.success('Lead deleted')
      fetchLeads()
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to delete lead')
    }
  }

  const handleEdit = (lead: Lead) => {
    setEditingLead(lead)
    setFormData({
      contact_id: lead.contact_id || '',
      company_id: lead.company_id || '',
      title: lead.title,
      description: lead.description || '',
      status: lead.status,
      owner_id: lead.owner_id || '',
      source: lead.source || '',
      source_id: lead.source_id || '',
      utm_source: lead.utm_source || '',
      utm_medium: lead.utm_medium || '',
      utm_campaign: lead.utm_campaign || '',
      utm_content: lead.utm_content || '',
      utm_term: lead.utm_term || '',
      referrer_url: lead.referrer_url || '',
      landing_page: lead.landing_page || '',
      custom_fields: lead.custom_fields || {},
    })
  }

  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement> | string, field?: string) => {
    if (typeof e === 'string') {
      setFormData((prev) => ({ ...prev, [field!]: e }))
    } else {
      const { name, value } = e.target
      setFormData((prev) => ({ ...prev, [name]: value }))
    }
  }

  const getStatusBadge = (status: string) => {
    const variants: Record<string, 'default' | 'secondary' | 'destructive' | 'outline'> = {
      new: 'secondary',
      contacted: 'default',
      qualified: 'default',
      proposal: 'default',
      negotiation: 'default',
      closed_won: 'default',
      closed_lost: 'destructive',
    }
    return (
      <Badge variant={variants[status] || 'secondary'} className="capitalize">
        {status.replace('_', ' ')}
      </Badge>
    )
  }

  const columns = [
    { key: 'title', header: 'Title', sortable: true, render: (row: Lead) => (
      <div>
        <p className="font-medium">{row.title}</p>
        {row.company && <p className="text-xs text-muted-foreground">{row.company.name}</p>}
        {row.contact && <p className="text-xs text-muted-foreground">{row.contact.first_name} {row.contact.last_name}</p>}
      </div>
    )},
    { key: 'status', header: 'Status', sortable: true, render: (row: Lead) => getStatusBadge(row.status) },
    { key: 'ai_score', header: 'AI Score', sortable: true, render: (row: Lead) => row.ai_score ? `${row.ai_score}/100` : '-' },
    { key: 'source', header: 'Source', sortable: true },
    { key: 'owner_id', header: 'Owner', sortable: false, render: (row: Lead) => row.owner ? `${row.owner.full_name}` : 'Unassigned' },
  ]

  const actions = [
    { label: 'View', icon: <Eye className="h-4 w-4" />, onClick: (row: Lead) => handleEdit(row) },
    { label: 'Edit', icon: <Edit className="h-4 w-4" />, onClick: (row: Lead) => handleEdit(row) },
    { label: 'Delete', icon: <Trash2 className="h-4 w-4" />, onClick: handleDelete, variant: 'destructive' as const },
  ]

  const handleSearch = (query: string) => {
    setSearchQuery(query)
    setPagination((prev) => ({ ...prev, page: 1 }))
  }

  const handlePageChange = (page: number) => setPagination((prev) => ({ ...prev, page }))
  const handlePageSizeChange = (pageSize: number) => setPagination((prev) => ({ ...prev, pageSize, page: 1 }))
  const handleSort = (key: string, order: 'asc' | 'desc') => console.log(`Sort by ${key} ${order}`)

  const openCreateDialog = () => { setEditingLead(null); setFormData(initialFormData) }

  const formFields = (
    <div className="grid gap-4 sm:grid-cols-2">
      <div className="sm:col-span-2">
        <Label htmlFor="title">Title *</Label>
        <Input id="title" name="title" value={formData.title} onChange={handleChange} required placeholder="Enterprise Deal - Acme Corp" />
      </div>
      <div>
        <Label htmlFor="status">Status *</Label>
        <Select value={formData.status} onValueChange={(value) => handleChange(value, 'status')}>
          <SelectTrigger><SelectValue placeholder="Select status" /></SelectTrigger>
          <SelectContent>
            {leadStatuses.map((s) => <SelectItem key={s} value={s}>{s.replace('_', ' ')}</SelectItem>)}
          </SelectContent>
        </Select>
      </div>
      <div>
        <Label htmlFor="company_id">Company</Label>
        <Select value={formData.company_id} onValueChange={(value) => handleChange(value, 'company_id')}>
          <SelectTrigger><SelectValue placeholder="Select company..." /></SelectTrigger>
          <SelectContent>
            <SelectItem value="">None</SelectItem>
            {companies.map((c) => <SelectItem key={c.id} value={c.id}>{c.name}</SelectItem>)}
          </SelectContent>
        </Select>
      </div>
      <div>
        <Label htmlFor="contact_id">Contact</Label>
        <Select value={formData.contact_id} onValueChange={(value) => handleChange(value, 'contact_id')}>
          <SelectTrigger><SelectValue placeholder="Select contact..." /></SelectTrigger>
          <SelectContent>
            <SelectItem value="">None</SelectItem>
            {contacts.map((c) => <SelectItem key={c.id} value={c.id}>{c.first_name} {c.last_name}</SelectItem>)}
          </SelectContent>
        </Select>
      </div>
      <div className="sm:col-span-2">
        <Label htmlFor="description">Description</Label>
        <textarea id="description" name="description" value={formData.description} onChange={handleChange} className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm" rows={3} placeholder="Lead details..." />
      </div>
      <div>
        <Label htmlFor="source">Source</Label>
        <Input id="source" name="source" value={formData.source} onChange={handleChange} placeholder="Website, Referral, etc." />
      </div>
      <div>
        <Label htmlFor="source_id">Source ID</Label>
        <Input id="source_id" name="source_id" value={formData.source_id} onChange={handleChange} placeholder="External reference ID" />
      </div>
    </div>
  )

  return (
    <div className="flex h-screen bg-background">
      <div className="flex-1 overflow-y-auto p-6 lg:p-8">
        <DataTable
          data={leads}
          columns={columns}
          isLoading={isLoading}
          emptyMessage="No leads found. Create your first lead to get started."
          title="Leads"
          subtitle="Track and qualify your sales opportunities"
          onAdd={openCreateDialog}
          actions={actions}
          pagination={pagination}
          sortBy=""
          sortOrder="asc"
          onSort={handleSort}
          searchPlaceholder="Search leads..."
          onSearch={handleSearch}
        />

        <Dialog open={!!editingLead || isCreating} onOpenChange={(open) => { if (!open) { setEditingLead(null); setFormData(initialFormData); } }}>
          <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
            <DialogHeader>
              <DialogTitle>{editingLead ? 'Edit Lead' : 'Create Lead'}</DialogTitle>
            </DialogHeader>
            <form onSubmit={editingLead ? handleUpdate : handleCreate}>
              {formFields}
              <DialogFooter className="gap-2">
                <Button type="button" variant="outline" onClick={() => { setEditingLead(null); setFormData(initialFormData); }}>
                  Cancel
                </Button>
                <Button type="submit" disabled={isCreating || isEditing}>
                  {isCreating || isEditing ? 'Saving...' : editingLead ? 'Update' : 'Create'}
                </Button>
              </DialogFooter>
            </form>
          </DialogContent>
        </Dialog>
      </div>
    </div>
  )
}