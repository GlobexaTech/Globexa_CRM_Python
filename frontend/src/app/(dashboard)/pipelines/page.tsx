'use client'

import { useState, useEffect } from 'react'
import { Plus, Search, GitBranch, Trash2, Edit, Eye, ChevronLeft, ChevronRight, GripVertical, Settings, X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Card, CardContent, CardHeader, CardTitle, CardFooter } from '@/components/ui/card'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { DataTable } from '@/components/data-table'
import { api, Pipeline, Stage } from '@/lib/api'
import { useAuth } from '@/lib/auth-context'
import { toast } from 'sonner'
import { Badge } from '@/components/ui/badge'

const initialPipelineData = {
  name: '',
  description: '',
  is_default: false,
  is_active: true,
}

const initialStageData = {
  pipeline_id: '',
  name: '',
  order: '',
  probability: '',
  is_closed: false,
  is_won: false,
  color: '#3b82f6',
}

export default function PipelinesPage() {
  const { tenant, isLoading: authLoading } = useAuth()
  const [pipelines, setPipelines] = useState<Pipeline[]>([])
  const [stages, setStages] = useState<Record<string, Stage[]>>({})
  const [isLoading, setIsLoading] = useState(true)
  const [isCreatingPipeline, setIsCreatingPipeline] = useState(false)
  const [isEditingPipeline, setIsEditingPipeline] = useState(false)
  const [editingPipeline, setEditingPipeline] = useState<Pipeline | null>(null)
  const [pipelineFormData, setPipelineFormData] = useState(initialPipelineData)
  const [selectedPipeline, setSelectedPipeline] = useState<string>('')
  const [isCreatingStage, setIsCreatingStage] = useState(false)
  const [stageFormData, setStageFormData] = useState(initialStageData)
  const [editingStage, setEditingStage] = useState<Stage | null>(null)

  useEffect(() => {
    if (!authLoading && tenant) {
      fetchPipelines()
    }
  }, [authLoading, tenant])

  const fetchPipelines = async () => {
    setIsLoading(true)
    try {
      const data = await api.listPipelines()
      setPipelines(data)
      if (data.length > 0 && !selectedPipeline) {
        setSelectedPipeline(data[0].id)
      }
      // Fetch stages for all pipelines
      for (const p of data) {
        const stagesData = await api.listStages(p.id)
        setStages((prev) => ({ ...prev, [p.id]: stagesData }))
      }
    } catch (error) {
      toast.error('Failed to load pipelines')
      console.error(error)
    } finally {
      setIsLoading(false)
    }
  }

  const handleCreatePipeline = async (e: React.FormEvent) => {
    e.preventDefault()
    setIsCreatingPipeline(true)
    try {
      const newPipeline = await api.createPipeline(pipelineFormData)
      toast.success('Pipeline created')
      setPipelineFormData(initialPipelineData)
      fetchPipelines()
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to create pipeline')
    } finally {
      setIsCreatingPipeline(false)
    }
  }

  const handleUpdatePipeline = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!editingPipeline) return
    setIsEditingPipeline(true)
    try {
      await api.updatePipeline(editingPipeline.id, pipelineFormData)
      toast.success('Pipeline updated')
      setEditingPipeline(null)
      setPipelineFormData(initialPipelineData)
      fetchPipelines()
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to update pipeline')
    } finally {
      setIsEditingPipeline(false)
    }
  }

  const handleDeletePipeline = async (pipeline: Pipeline) => {
    if (!confirm(`Delete pipeline "${pipeline.name}" and all its stages?`)) return
    try {
      // Note: API doesn't have delete pipeline endpoint yet
      toast.error('Delete pipeline not implemented in API yet')
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to delete pipeline')
    }
  }

  const handleEditPipeline = (pipeline: Pipeline) => {
    setEditingPipeline(pipeline)
    setPipelineFormData({
      name: pipeline.name,
      description: pipeline.description || '',
      is_default: pipeline.is_default,
      is_active: pipeline.is_active,
    })
  }

  const handleCreateStage = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!selectedPipeline) return
    setIsCreatingStage(true)
    try {
      // API doesn't have create stage endpoint yet - would need to add
      toast.error('Create stage endpoint not implemented in API yet')
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to create stage')
    } finally {
      setIsCreatingStage(false)
    }
  }

  const handleStageChange = (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
    const { name, value } = e.target
    setStageFormData((prev) => ({ ...prev, [name]: value }))
  }

  const pipelineColumns = [
    { key: 'name', header: 'Name', sortable: true },
    { key: 'description', header: 'Description', render: (row: Pipeline) => row.description || '-' },
    { key: 'is_default', header: 'Default', render: (row: Pipeline) => row.is_default ? <Badge variant="default">Yes</Badge> : <Badge variant="secondary">No</Badge> },
    { key: 'is_active', header: 'Active', render: (row: Pipeline) => row.is_active ? <Badge variant="default">Active</Badge> : <Badge variant="secondary">Inactive</Badge> },
    { key: 'stages_count', header: 'Stages', render: (row: Pipeline) => stages[row.id]?.length || 0 },
  ]

  const pipelineActions = [
    { label: 'View Stages', icon: <GitBranch className="h-4 w-4" />, onClick: (row: Pipeline) => setSelectedPipeline(row.id) },
    { label: 'Edit', icon: <Edit className="h-4 w-4" />, onClick: handleEditPipeline },
    { label: 'Delete', icon: <Trash2 className="h-4 w-4" />, onClick: handleDeletePipeline, variant: 'destructive' as const },
  ]

  return (
    <div className="flex h-screen bg-background">
      <div className="flex-1 overflow-y-auto p-6 lg:p-8">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 mb-6">
          <div>
            <h1 className="text-3xl font-bold tracking-tight">Pipelines</h1>
            <p className="text-muted-foreground mt-1">Manage your sales pipelines and stages</p>
          </div>
          <Button onClick={() => { setEditingPipeline(null); setPipelineFormData(initialPipelineData); }}>
            <Plus className="mr-2 h-4 w-4" />
            Add Pipeline
          </Button>
        </div>

        {/* Pipelines Table */}
        <Card className="mb-8">
          <CardHeader>
            <CardTitle>Sales Pipelines</CardTitle>
          </CardHeader>
          <CardContent>
            <DataTable
              data={pipelines}
              columns={pipelineColumns}
              isLoading={isLoading}
              emptyMessage="No pipelines found. Create your first pipeline to get started."
              actions={pipelineActions}
              sortBy=""
              sortOrder="asc"
              onSort={() => {}}
              searchPlaceholder="Search pipelines..."
              onSearch={() => {}}
            />
          </CardContent>
        </Card>

        {/* Stages for Selected Pipeline */}
        {selectedPipeline && (
          <div>
            <div className="flex items-center justify-between mb-4">
              <div>
                <h2 className="text-xl font-semibold">
                  Stages for {pipelines.find(p => p.id === selectedPipeline)?.name || 'Pipeline'}
                </h2>
                <p className="text-muted-foreground">Drag to reorder stages</p>
              </div>
              <Button onClick={() => { setEditingStage(null); setStageFormData({ ...initialStageData, pipeline_id: selectedPipeline }); }}>
                <Plus className="mr-2 h-4 w-4" />
                Add Stage
              </Button>
            </div>

            <div className="flex gap-4 overflow-x-auto pb-4">
              {(stages[selectedPipeline] || []).map((stage) => (
                <StageCard
                  key={stage.id}
                  stage={stage}
                  onEdit={() => {
                    setEditingStage(stage)
                    setStageFormData({
                      pipeline_id: stage.pipeline_id,
                      name: stage.name,
                      order: stage.order.toString(),
                      probability: stage.probability.toString(),
                      is_closed: stage.is_closed,
                      is_won: stage.is_won,
                      color: stage.color || '#3b82f6',
                    })
                  }}
                  onDelete={() => { /* TODO */ }}
                />
              ))}

              {/* Add Stage Card */}
              <div className="flex-shrink-0 w-64">
                <Card className="border-dashed h-[200px] flex items-center justify-center">
                  <CardContent className="text-center">
                    <Button variant="outline" className="w-full h-full flex-col gap-2" onClick={() => { setEditingStage(null); setStageFormData({ ...initialStageData, pipeline_id: selectedPipeline }); }}>
                      <Plus className="h-8 w-8 text-muted-foreground" />
                      <span className="text-muted-foreground">Add Stage</span>
                    </Button>
                  </CardContent>
                </Card>
              </div>
            </div>
          </div>
        )}

        {/* Pipeline Dialog */}
        <Dialog open={!!editingPipeline || isCreatingPipeline} onOpenChange={(open) => { if (!open) { setEditingPipeline(null); setPipelineFormData(initialPipelineData); } }}>
          <DialogContent className="max-w-md">
            <DialogHeader>
              <DialogTitle>{editingPipeline ? 'Edit Pipeline' : 'Create Pipeline'}</DialogTitle>
            </DialogHeader>
            <form onSubmit={editingPipeline ? handleUpdatePipeline : handleCreatePipeline}>
              <div className="grid gap-4 py-4">
                <div>
                  <Label htmlFor="name">Name *</Label>
                  <Input id="name" name="name" value={pipelineFormData.name} onChange={(e) => setPipelineFormData({...pipelineFormData, name: e.target.value})} required placeholder="Enterprise Sales" />
                </div>
                <div>
                  <Label htmlFor="description">Description</Label>
                  <Input id="description" name="description" value={pipelineFormData.description} onChange={(e) => setPipelineFormData({...pipelineFormData, description: e.target.value})} placeholder="Main sales pipeline" />
                </div>
                <div className="flex items-center gap-4">
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input type="checkbox" checked={pipelineFormData.is_default} onChange={(e) => setPipelineFormData({...pipelineFormData, is_default: e.target.checked})} className="h-4 w-4 rounded border-input" />
                    <span className="text-sm">Set as default</span>
                  </label>
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input type="checkbox" checked={pipelineFormData.is_active} onChange={(e) => setPipelineFormData({...pipelineFormData, is_active: e.target.checked})} className="h-4 w-4 rounded border-input" />
                    <span className="text-sm">Active</span>
                  </label>
                </div>
              </div>
              <DialogFooter className="gap-2">
                <Button type="button" variant="outline" onClick={() => { setEditingPipeline(null); setPipelineFormData(initialPipelineData); }}>
                  Cancel
                </Button>
                <Button type="submit" disabled={isCreatingPipeline || isEditingPipeline}>
                  {isCreatingPipeline || isEditingPipeline ? 'Saving...' : editingPipeline ? 'Update' : 'Create'}
                </Button>
              </DialogFooter>
            </form>
          </DialogContent>
        </Dialog>

        {/* Stage Dialog */}
        <Dialog open={!!editingStage || isCreatingStage} onOpenChange={(open) => { if (!open) { setEditingStage(null); setStageFormData(initialStageData); } }}>
          <DialogContent className="max-w-md">
            <DialogHeader>
              <DialogTitle>{editingStage ? 'Edit Stage' : 'Create Stage'}</DialogTitle>
            </DialogHeader>
            <form onSubmit={handleCreateStage}>
              <div className="grid gap-4 py-4">
                <div>
                  <Label htmlFor="stage_name">Name *</Label>
                  <Input id="stage_name" name="name" value={stageFormData.name} onChange={handleStageChange} required placeholder="Qualification" />
                </div>
                <div>
                  <Label htmlFor="order">Order *</Label>
                  <Input id="order" name="order" type="number" value={stageFormData.order} onChange={handleStageChange} required placeholder="0" />
                </div>
                <div>
                  <Label htmlFor="probability">Probability (%)</Label>
                  <Input id="probability" name="probability" type="number" min="0" max="100" value={stageFormData.probability} onChange={handleStageChange} placeholder="25" />
                </div>
                <div>
                  <Label htmlFor="color">Color</Label>
                  <Input id="color" name="color" type="color" value={stageFormData.color} onChange={handleStageChange} />
                </div>
                <div className="flex items-center gap-4">
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input type="checkbox" checked={stageFormData.is_closed} onChange={(e) => setStageFormData({...stageFormData, is_closed: e.target.checked})} className="h-4 w-4 rounded border-input" />
                    <span className="text-sm">Closed</span>
                  </label>
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input type="checkbox" checked={stageFormData.is_won} onChange={(e) => setStageFormData({...stageFormData, is_won: e.target.checked})} className="h-4 w-4 rounded border-input" />
                    <span className="text-sm">Won</span>
                  </label>
                </div>
              </div>
              <DialogFooter className="gap-2">
                <Button type="button" variant="outline" onClick={() => { setEditingStage(null); setStageFormData(initialStageData); }}>
                  Cancel
                </Button>
                <Button type="submit" disabled={isCreatingStage}>
                  {isCreatingStage ? 'Saving...' : editingStage ? 'Update' : 'Create'}
                </Button>
              </DialogFooter>
            </form>
          </DialogContent>
        </Dialog>
      </div>
    </div>
  )
}

// Stage Card Component
function StageCard({ stage, onEdit, onDelete }: { stage: Stage; onEdit: () => void; onDelete: () => void }) {
  return (
    <Card className="w-64 flex-shrink-0 h-[350px] flex flex-col" style={{ borderTop: `3px solid ${stage.color || '#3b82f6'}` }}>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="text-lg">{stage.name}</CardTitle>
          <Badge variant={stage.is_won ? 'default' : stage.is_closed ? 'destructive' : 'secondary'}>
            {stage.is_won ? 'Won' : stage.is_closed ? 'Lost' : 'Open'}
          </Badge>
        </div>
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <span>Order: {stage.order}</span>
          <span>Prob: {stage.probability}%</span>
        </div>
      </CardHeader>
      <CardContent className="flex-1">
        <div className="text-center text-muted-foreground py-8">
          {stage.deals_count} deals
        </div>
      </CardContent>
      <CardFooter className="flex justify-between p-0 pt-2">
        <Button variant="ghost" size="sm" onClick={onEdit}>
          <Edit className="h-3 w-3" />
        </Button>
        <Button variant="ghost" size="sm" onClick={onDelete} className="text-destructive hover:text-destructive">
          <Trash2 className="h-3 w-3" />
        </Button>
      </CardFooter>
    </Card>
  )
}