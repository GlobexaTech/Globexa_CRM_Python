'use client'

import { useState, useEffect } from 'react'
import { Plus, Search, Briefcase, Trash2, Edit, Eye, DollarSign, ChevronLeft, ChevronRight, GripVertical } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { DataTable } from '@/components/data-table'
import { api, Deal, Pipeline, Stage, Company, Contact } from '@/lib/api'
import { useAuth } from '@/lib/auth-context'
import { toast } from 'sonner'
import { Badge } from '@/components/ui/badge'

const initialFormData = {
  pipeline_id: '',
  stage_id: '',
  contact_id: '',
  company_id: '',
  lead_id: '',
  title: '',
  description: '',
  value: '',
  currency: 'USD',
  owner_id: '',
  expected_close_date: '',
  probability: '',
  source: '',
  custom_fields: {},
}

export default function DealsPage() {
  const { tenant, isLoading: authLoading } = useAuth()
  const [deals, setDeals] = useState<Deal[]>([])
  const [pipelines, setPipelines] = useState<Pipeline[]>([])
  const [stages, setStages] = useState<Record<string, Stage[]>>({})
  const [companies, setCompanies] = useState<Company[]>([])
  const [contacts, setContacts] = useState<Contact[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [isCreating, setIsCreating] = useState(false)
  const [isEditing, setIsEditing] = useState(false)
  const [editingDeal, setEditingDeal] = useState<Deal | null>(null)
  const [formData, setFormData] = useState(initialFormData)
  const [pagination, setPagination] = useState({ page: 1, pageSize: 25, total: 0, onPageChange: (page: number) => setPagination(p => ({...p, page})), onPageSizeChange: (pageSize: number) => setPagination(p => ({...p, pageSize, page: 1})) })
  const [searchQuery, setSearchQuery] = useState('')
  const [viewMode, setViewMode] = useState<'table' | 'kanban'>('kanban')
  const [selectedPipeline, setSelectedPipeline] = useState<string>('')

  useEffect(() => {
    if (!authLoading && tenant) {
      fetchDeals()
      fetchPipelines()
      fetchCompanies()
      fetchContacts()
    }
  }, [authLoading, tenant, pagination.page, pagination.pageSize, searchQuery, selectedPipeline])

  const fetchDeals = async () => {
    setIsLoading(true)
    try {
      const response = await api.listDeals({
        page: pagination.page,
        page_size: pagination.pageSize,
      })
      setDeals(response.items)
      setPagination((prev) => ({ ...prev, total: response.total }))
    } catch (error) {
      toast.error('Failed to load deals')
      console.error(error)
    } finally {
      setIsLoading(false)
    }
  }

  const fetchPipelines = async () => {
    try {
      const data = await api.listPipelines()
      setPipelines(data)
      if (data.length > 0 && !selectedPipeline) {
        setSelectedPipeline(data[0].id)
        // Fetch stages for first pipeline
        const stagesData = await api.listStages(data[0].id)
        setStages((prev) => ({ ...prev, [data[0].id]: stagesData }))
      }
      // Fetch stages for all pipelines
      for (const p of data) {
        const stagesData = await api.listStages(p.id)
        setStages((prev) => ({ ...prev, [p.id]: stagesData }))
      }
    } catch (error) {
      console.error('Failed to load pipelines:', error)
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
      const payload = { ...formData, value: Number(formData.value), probability: Number(formData.probability) }
      await api.createDeal(payload)
      toast.success('Deal created')
      setFormData(initialFormData)
      fetchDeals()
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to create deal')
    } finally {
      setIsCreating(false)
    }
  }

  const handleUpdate = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!editingDeal) return
    setIsEditing(true)
    try {
      const payload = { ...formData, value: Number(formData.value), probability: Number(formData.probability) }
      await api.updateDeal(editingDeal.id, payload)
      toast.success('Deal updated')
      setEditingDeal(null)
      setFormData(initialFormData)
      fetchDeals()
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to update deal')
    } finally {
      setIsEditing(false)
    }
  }

  const handleDelete = async (deal: Deal) => {
    if (!confirm(`Delete ${deal.title}?`)) return
    try {
      await api.deleteDeal(deal.id)
      toast.success('Deal deleted')
      fetchDeals()
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to delete deal')
    }
  }

  const handleEdit = (deal: Deal) => {
    setEditingDeal(deal)
    setFormData({
      pipeline_id: deal.pipeline_id,
      stage_id: deal.stage_id,
      contact_id: deal.contact_id || '',
      company_id: deal.company_id || '',
      lead_id: deal.lead_id || '',
      title: deal.title,
      description: deal.description || '',
      value: deal.value.toString(),
      currency: deal.currency,
      owner_id: deal.owner_id || '',
      expected_close_date: deal.expected_close_date?.split('T')[0] || '',
      probability: deal.probability.toString(),
      source: deal.source || '',
      custom_fields: deal.custom_fields || {},
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

  const getStageForDeal = (deal: Deal) => {
    return stages[deal.pipeline_id]?.find(s => s.id === deal.stage_id)
  }

  const getPipelineStages = (pipelineId: string) => {
    return stages[pipelineId] || []
  }

  // Kanban view
  if (viewMode === 'kanban') {
    const pipelineStages = getPipelineStages(selectedPipeline)
    const pipelineDeals = deals.filter(d => d.pipeline_id === selectedPipeline)

    return (
      <div className="flex h-screen bg-background">
        <div className="flex-1 overflow-auto p-6 lg:p-8">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 mb-6">
            <div>
              <h1 className="text-3xl font-bold tracking-tight">Deals Pipeline</h1>
              <p className="text-muted-foreground mt-1">Visualize and manage your sales pipeline</p>
            </div>
            <div className="flex items-center gap-4">
              <Select value={selectedPipeline} onValueChange={setSelectedPipeline}>
                <SelectTrigger className="w-[250px]">
                  <SelectValue placeholder="Select pipeline" />
                </SelectTrigger>
                <SelectContent>
                  {pipelines.map((p) => <SelectItem key={p.id} value={p.id}>{p.name}{p.is_default && ' (Default)'}</SelectItem>)}
                </SelectContent>
              </Select>
              <div className="flex gap-2">
                <Button variant="outline" size="sm" onClick={() => setViewMode('table')}>
                  List View
                </Button>
                <Button onClick={() => { setEditingDeal(null); setFormData({ ...initialFormData, pipeline_id: selectedPipeline }); }}>
                  <Plus className="mr-2 h-4 w-4" />
                  Add Deal
                </Button>
              </div>
            </div>
          </div>

          {pipelineStages.length === 0 ? (
            <div className="flex items-center justify-center h-64">
              <div className="text-center text-muted-foreground">
                <Briefcase className="h-12 w-12 mx-auto mb-4 opacity-50" />
                <p>No stages found for this pipeline. Configure stages in Pipelines.</p>
              </div>
            </div>
          ) : (
            <div className="flex gap-4 overflow-x-auto pb-4 min-h-[500px]">
              {pipelineStages.map((stage) => {
                const stageDeals = pipelineDeals.filter(d => d.stage_id === stage.id)
                const stageValue = stageDeals.reduce((sum, d) => sum + d.value, 0)
                return (
                  <div key={stage.id} className="flex-shrink-0 w-80 bg-muted/50 rounded-lg h-full max-h-[calc(100vh-300px)] flex flex-col">
                    <div className="p-3 border-b flex items-center justify-between" style={{ borderTop: `3px solid ${stage.color || '#3b82f6'}` }}>
                      <div className="flex items-center gap-2">
                        <h3 className="font-semibold text-sm truncate">{stage.name}</h3>
                        <Badge variant="secondary">{stageDeals.length}</Badge>
                      </div>
                      <div className="text-right">
                        <p className="text-xs text-muted-foreground">Total Value</p>
                        <p className="font-semibold">${stageValue.toLocaleString()}</p>
                      </div>
                    </div>
                    <div className="flex-1 overflow-y-auto p-2 space-y-2 min-h-[200px]">
                      {stageDeals.length === 0 && (
                        <div className="text-center text-muted-foreground text-sm py-8">
                          Drop deals here
                        </div>
                      )}
                      {stageDeals.map((deal) => (
                        <DealCard key={deal.id} deal={deal} onEdit={handleEdit} onDelete={handleDelete} />
                      ))}
                    </div>
                    <Button variant="outline" size="sm" className="mx-2 mb-2" onClick={() => { setEditingDeal(null); setFormData({ ...initialFormData, pipeline_id: selectedPipeline, stage_id: stage.id }); }}>
                      <Plus className="mr-1 h-3 w-3" />
                      Add Deal
                    </Button>
                  </div>
                )
              })}
              {/* Add new stage button */}
              <div className="flex-shrink-0 w-80">
                <Button variant="outline" className="w-full h-full min-h-[200px] flex-col gap-2" onClick={() => { /* TODO: add stage */ }}>
                  <Plus className="h-8 w-8 text-muted-foreground" />
                  <span className="text-muted-foreground">Add Stage</span>
                </Button>
              </div>
            </div>
          )}
        </div>
      </div>
    )
  }

  // Table view
  const tableColumns = [
    { key: 'title', header: 'Deal', sortable: true, render: (row: Deal) => (
      <div>
        <p className="font-medium">{row.title}</p>
        {row.company && <p className="text-xs text-muted-foreground">{row.company.name}</p>}
        {row.contact && <p className="text-xs text-muted-foreground">{row.contact.first_name} {row.contact.last_name}</p>}
      </div>
    )},
    { key: 'stage', header: 'Stage', sortable: true, render: (row: Deal) => {
      const stage = getStageForDeal(row)
      return stage ? (
        <Badge variant="secondary" style={{ backgroundColor: stage.color || '#3b82f6' }}>
          {stage.name}
        </Badge>
      ) : '-'
    }},
    { key: 'value', header: 'Value', sortable: true, render: (row: Deal) => (
      <div className="flex items-center gap-1">
        <DollarSign className="h-3 w-3 text-muted-foreground" />
        <span className="font-medium">{row.currency} {row.value.toLocaleString()}</span>
      </div>
    )},
    { key: 'probability', header: 'Probability', sortable: true, render: (row: Deal) => `${row.probability}%` },
    { key: 'expected_close_date', header: 'Close Date', sortable: true, render: (row: Deal) => row.expected_close_date ? row.expected_close_date.split('T')[0] : '-' },
    { key: 'owner_id', header: 'Owner', sortable: false, render: (row: Deal) => row.owner ? row.owner.full_name : 'Unassigned' },
  ]

  const actions = [
    { label: 'View', icon: <Eye className="h-4 w-4" />, onClick: (row: Deal) => handleEdit(row) },
    { label: 'Edit', icon: <Edit className="h-4 w-4" />, onClick: (row: Deal) => handleEdit(row) },
    { label: 'Delete', icon: <Trash2 className="h-4 w-4" />, onClick: handleDelete, variant: 'destructive' as const },
  ]

  const handleSearch = (query: string) => { setSearchQuery(query); setPagination((prev) => ({ ...prev, page: 1 })) }
  const handlePageChange = (page: number) => setPagination((prev) => ({ ...prev, page }))
  const handlePageSizeChange = (pageSize: number) => setPagination((prev) => ({ ...prev, pageSize, page: 1 }))
  const handleSort = (key: string, order: 'asc' | 'desc') => console.log(`Sort by ${key} ${order}`)
  const openCreateDialog = () => { setEditingDeal(null); setFormData({ ...initialFormData, pipeline_id: selectedPipeline }) }

  return (
    <div className="flex h-screen bg-background">
      <div className="flex-1 overflow-y-auto p-6 lg:p-8">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 mb-6">
          <div>
            <h1 className="text-3xl font-bold tracking-tight">Deals</h1>
            <p className="text-muted-foreground mt-1">Manage and track your deals</p>
          </div>
          <div className="flex items-center gap-4">
            <Select value={selectedPipeline} onValueChange={setSelectedPipeline}>
              <SelectTrigger className="w-[250px]"><SelectValue placeholder="Filter by pipeline" /></SelectTrigger>
              <SelectContent>
                {pipelines.map((p) => <SelectItem key={p.id} value={p.id}>{p.name}</SelectItem>)}
              </SelectContent>
            </Select>
            <div className="flex gap-2">
              <Button variant="outline" size="sm" onClick={() => setViewMode('kanban')}>
                Kanban
              </Button>
              <Button onClick={openCreateDialog}>
                <Plus className="mr-2 h-4 w-4" />
                Add Deal
              </Button>
            </div>
          </div>
        </div>

        <DataTable
          data={deals}
          columns={tableColumns}
          isLoading={isLoading}
          emptyMessage="No deals found. Create your first deal to get started."
          title="Deals"
          subtitle="Track and manage your sales opportunities"
          onAdd={openCreateDialog}
          actions={actions}
          pagination={pagination}
          sortBy=""
          sortOrder="asc"
          onSort={handleSort}
          searchPlaceholder="Search deals..."
          onSearch={handleSearch}
        />

        <Dialog open={!!editingDeal || isCreating} onOpenChange={(open) => { if (!open) { setEditingDeal(null); setFormData(initialFormData); } }}>
          <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
            <DialogHeader>
              <DialogTitle>{editingDeal ? 'Edit Deal' : 'Create Deal'}</DialogTitle>
            </DialogHeader>
            <form onSubmit={editingDeal ? handleUpdate : handleCreate}>
              <div className="grid gap-4 sm:grid-cols-2">
                <div>
                  <Label htmlFor="pipeline_id">Pipeline *</Label>
                  <Select value={formData.pipeline_id} onValueChange={(value) => handleChange(value, 'pipeline_id')}>
                    <SelectTrigger><SelectValue placeholder="Select pipeline" /></SelectTrigger>
                    <SelectContent>
                      {pipelines.map((p) => <SelectItem key={p.id} value={p.id}>{p.name}</SelectItem>)}
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <Label htmlFor="stage_id">Stage *</Label>
                  <Select value={formData.stage_id} onValueChange={(value) => handleChange(value, 'stage_id')}>
                    <SelectTrigger><SelectValue placeholder="Select stage" /></SelectTrigger>
                    <SelectContent>
                      {stages[formData.pipeline_id]?.map((s) => <SelectItem key={s.id} value={s.id}>{s.name}</SelectItem>) || []}
                    </SelectContent>
                  </Select>
                </div>
                <div className="sm:col-span-2">
                  <Label htmlFor="title">Title *</Label>
                  <Input id="title" name="title" value={formData.title} onChange={handleChange} required placeholder="Enterprise License - Acme Corp" />
                </div>
                <div>
                  <Label htmlFor="value">Value *</Label>
                  <Input id="value" name="value" type="number" value={formData.value} onChange={handleChange} required placeholder="50000" />
                </div>
                <div>
                  <Label htmlFor="currency">Currency</Label>
                  <Select value={formData.currency} onValueChange={handleChange}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="USD">USD</SelectItem>
                      <SelectItem value="EUR">EUR</SelectItem>
                      <SelectItem value="GBP">GBP</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <Label htmlFor="probability">Probability (%)</Label>
                  <Input id="probability" name="probability" type="number" min="0" max="100" value={formData.probability} onChange={handleChange} placeholder="50" />
                </div>
                <div>
                  <Label htmlFor="expected_close_date">Expected Close Date</Label>
                  <Input id="expected_close_date" name="expected_close_date" type="date" value={formData.expected_close_date} onChange={handleChange} />
                </div>
                <div className="sm:col-span-2">
                  <Label htmlFor="company_id">Company</Label>
                  <Select value={formData.company_id} onValueChange={handleChange}>
                    <SelectTrigger><SelectValue placeholder="Select company..." /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="">None</SelectItem>
                      {companies.map((c) => <SelectItem key={c.id} value={c.id}>{c.name}</SelectItem>)}
                    </SelectContent>
                  </Select>
                </div>
                <div className="sm:col-span-2">
                  <Label htmlFor="contact_id">Contact</Label>
                  <Select value={formData.contact_id} onValueChange={handleChange}>
                    <SelectTrigger><SelectValue placeholder="Select contact..." /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="">None</SelectItem>
                      {contacts.map((c) => <SelectItem key={c.id} value={c.id}>{c.first_name} {c.last_name}</SelectItem>)}
                    </SelectContent>
                  </Select>
                </div>
                <div className="sm:col-span-2">
                  <Label htmlFor="description">Description</Label>
                  <textarea id="description" name="description" value={formData.description} onChange={handleChange} className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm" rows={3} placeholder="Deal details..." />
                </div>
              </div>
              <DialogFooter className="gap-2">
                <Button type="button" variant="outline" onClick={() => { setEditingDeal(null); setFormData(initialFormData); }}>
                  Cancel
                </Button>
                <Button type="submit" disabled={isCreating || isEditing}>
                  {isCreating || isEditing ? 'Saving...' : editingDeal ? 'Update' : 'Create'}
                </Button>
              </DialogFooter>
            </form>
          </DialogContent>
        </Dialog>
      </div>
    </div>
  )
}

// Deal Card Component for Kanban
function DealCard({ deal, onEdit, onDelete }: { deal: Deal; onEdit: (d: Deal) => void; onDelete: (d: Deal) => void }) {
  return (
    <Card className="cursor-pointer hover:shadow-md transition-shadow" onClick={() => onEdit(deal)}>
      <CardContent className="p-3">
        <div className="flex items-start justify-between gap-2">
          <div className="flex-1 min-w-0">
            <p className="font-medium text-sm truncate">{deal.title}</p>
            {deal.company && <p className="text-xs text-muted-foreground truncate">{deal.company.name}</p>}
            {deal.contact && <p className="text-xs text-muted-foreground truncate">{deal.contact.first_name} {deal.contact.last_name}</p>}
          </div>
          <div className="flex items-center gap-1">
            <DollarSign className="h-3 w-3 text-muted-foreground" />
            <span className="text-sm font-semibold text-primary">{deal.currency} {deal.value.toLocaleString()}</span>
          </div>
        </div>
        <div className="mt-2 flex items-center justify-between">
          <Badge variant="secondary">{deal.probability}%</Badge>
          {deal.expected_close_date && (
            <span className="text-xs text-muted-foreground">{deal.expected_close_date.split('T')[0]}</span>
          )}
        </div>
      </CardContent>
    </Card>
  )
}