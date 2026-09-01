'use client'

import { ReactNode } from 'react'
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
  TableCaption,
} from '@/components/ui/table'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { ChevronDown, ChevronUp, ChevronLeft, ChevronRight, Loader2, Search, Filter, Plus, MoreHorizontal } from 'lucide-react'
import { cn } from '@/lib/utils'
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger, DropdownMenuSeparator } from '@/components/ui/dropdown-menu'

interface Column<T> {
  key: string
  header: string
  render?: (row: T) => ReactNode
  sortable?: boolean
  width?: string
}

interface DataTableProps<T> {
  data: T[]
  columns: Column<T>[]
  isLoading?: boolean
  emptyMessage?: string
  onRowClick?: (row: T) => void
  selection?: string[]
  onSelectionChange?: (ids: string[]) => void
  searchPlaceholder?: string
  onSearch?: (query: string) => void
  onFilter?: (filters: Record<string, string>) => void
  filters?: Record<string, { label: string; options: { value: string; label: string }[] }>
  sortBy?: string
  sortOrder?: 'asc' | 'desc'
  onSort?: (key: string, order: 'asc' | 'desc') => void
  actions?: {
    label: string
    icon: ReactNode
    onClick: (row: T) => void
    variant?: 'default' | 'destructive'
  }[]
  pagination?: {
    page: number
    pageSize: number
    total: number
    onPageChange: (page: number) => void
    onPageSizeChange: (pageSize: number) => void
  }
  title?: string
  subtitle?: string
  onAdd?: () => void
}

export function DataTable<T extends { id: string }>({
  data,
  columns,
  isLoading = false,
  emptyMessage = 'No data available',
  onRowClick,
  selection = [],
  onSelectionChange,
  searchPlaceholder = 'Search...',
  onSearch,
  onFilter,
  filters,
  sortBy,
  sortOrder,
  onSort,
  actions,
  pagination,
  title,
  subtitle,
  onAdd,
}: DataTableProps<T>) {
  const [searchQuery, setSearchQuery] = useState('')

  const handleSearch = (value: string) => {
    setSearchQuery(value)
    onSearch?.(value)
  }

  const handleSort = (key: string) => {
    if (!onSort) return
    const newOrder = sortBy === key && sortOrder === 'asc' ? 'desc' : 'asc'
    onSort(key, newOrder)
  }

  const handleSelectAll = () => {
    if (selection.length === data.length) {
      onSelectionChange?.([])
    } else {
      onSelectionChange?.(data.map((row) => row.id))
    }
  }

  const handleSelectRow = (id: string) => {
    if (selection.includes(id)) {
      onSelectionChange?.(selection.filter((s) => s !== id))
    } else {
      onSelectionChange?.([...selection, id])
    }
  }

  const isAllSelected = selection.length === data.length && data.length > 0

  return (
    <div className="space-y-4">
      {(title || subtitle || onAdd) && (
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <div>
            {title && <h2 className="text-xl font-semibold">{title}</h2>}
            {subtitle && <p className="text-sm text-muted-foreground">{subtitle}</p>}
          </div>
          {onAdd && (
            <Button onClick={onAdd} size="sm">
              <Plus className="mr-2 h-4 w-4" />
              Add
            </Button>
          )}
        </div>
      )}

      {(onSearch || filters) && (
        <div className="flex flex-col sm:flex-row gap-4">
          {onSearch && (
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
              <Input
                placeholder={searchPlaceholder}
                value={searchQuery}
                onChange={(e) => handleSearch(e.target.value)}
                className="pl-10"
              />
            </div>
          )}
          {filters && Object.entries(filters).map(([key, filter]) => (
            <Select
              key={key}
              value={""}
              onValueChange={(value) => onFilter?.({ ...{}, [key]: value })}
            >
              <SelectTrigger className="w-[180px]">
                <Filter className="mr-2 h-4 w-4" />
                <SelectValue placeholder={filter.label} />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="">All</SelectItem>
                {filter.options.map((opt) => (
                  <SelectItem key={opt.value} value={opt.value}>
                    {opt.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          ))}
        </div>
      )}

      <div className="rounded-md border">
        <Table>
          {title && <TableCaption>{title}</TableCaption>}
          <TableHeader>
            <TableRow>
              {onSelectionChange && (
                <TableHead className="w-12">
                  <input
                    type="checkbox"
                    checked={isAllSelected}
                    onChange={handleSelectAll}
                    className="h-4 w-4 rounded border-input"
                  />
                </TableHead>
              )}
              {columns.map((column) => (
                <TableHead
                  key={column.key}
                  className={cn(
                    column.sortable && 'cursor-pointer select-none hover:bg-accent',
                    column.width && column.width
                  )}
                  onClick={() => column.sortable && handleSort(column.key)}
                  style={{ width: column.width }}
                >
                  <div className="flex items-center gap-1">
                    {column.header}
                    {column.sortable && sortBy === column.key && (
                      sortOrder === 'asc' ? (
                        <ChevronUp className="h-4 w-4" />
                      ) : (
                        <ChevronDown className="h-4 w-4" />
                      )
                    )}
                  </div>
                </TableHead>
              ))}
              {actions && actions.length > 0 && (
                <TableHead className="w-40 text-right">Actions</TableHead>
              )}
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading ? (
              <TableRow>
                <TableCell colSpan={columns.length + (onSelectionChange ? 1 : 0) + (actions ? 1 : 0)} className="text-center py-8">
                  <Loader2 className="mx-auto h-8 w-8 animate-spin text-muted-foreground" />
                </TableCell>
              </TableRow>
            ) : data.length === 0 ? (
              <TableRow>
                <TableCell colSpan={columns.length + (onSelectionChange ? 1 : 0) + (actions ? 1 : 0)} className="text-center py-8">
                  <p className="text-muted-foreground">{emptyMessage}</p>
                </TableCell>
              </TableRow>
            ) : (
              data.map((row) => (
                <TableRow
                  key={row.id}
                  className={cn(
                    onRowClick && 'cursor-pointer hover:bg-accent/50',
                    selection.includes(row.id) && 'bg-accent'
                  )}
                  onClick={() => onRowClick?.(row)}
                >
                  {onSelectionChange && (
                    <TableCell className="w-12">
                      <input
                        type="checkbox"
                        checked={selection.includes(row.id)}
                        onChange={() => handleSelectRow(row.id)}
                        onClick={(e) => e.stopPropagation()}
                        className="h-4 w-4 rounded border-input"
                      />
                    </TableCell>
                  )}
                  {columns.map((column) => (
                    <TableCell key={column.key} className={cn(column.width && column.width)}>
                      {column.render ? column.render(row) : (row as any)[column.key]}
                    </TableCell>
                  ))}
                  {actions && actions.length > 0 && (
                    <TableCell className="text-right">
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <Button variant="ghost" className="h-8 w-8 p-0" size="icon">
                            <MoreHorizontal className="h-4 w-4" />
                          </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end">
                          {actions.map((action, index) => (
                            <DropdownMenuItem
                              key={index}
                              onClick={() => action.onClick(row)}
                              className={cn(action.variant === 'destructive' && 'text-destructive focus:text-destructive')}
                            >
                              {action.icon}
                              <span className="ml-2">{action.label}</span>
                            </DropdownMenuItem>
                          ))}
                        </DropdownMenuContent>
                      </DropdownMenu>
                    </TableCell>
                  )}
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>

      {pagination && (
        <div className="flex items-center justify-between">
          <div className="text-sm text-muted-foreground">
            Showing {((pagination.page - 1) * pagination.pageSize) + 1} to{' '}
            {Math.min(pagination.page * pagination.pageSize, pagination.total)} of{' '}
            {pagination.total} results
          </div>
          <div className="flex items-center gap-2">
            <Select value={pagination.pageSize.toString()} onValueChange={(v) => pagination.onPageSizeChange(Number(v))}>
              <SelectTrigger className="w-[100px]">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="10">10 per page</SelectItem>
                <SelectItem value="25">25 per page</SelectItem>
                <SelectItem value="50">50 per page</SelectItem>
                <SelectItem value="100">100 per page</SelectItem>
              </SelectContent>
            </Select>
            <Button
              variant="outline"
              size="sm"
              onClick={() => pagination.onPageChange(pagination.page - 1)}
              disabled={pagination.page === 1}
            >
              <ChevronLeft className="h-4 w-4" />
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => pagination.onPageChange(pagination.page + 1)}
              disabled={pagination.page * pagination.pageSize >= pagination.total}
            >
              <ChevronRight className="h-4 w-4" />
            </Button>
          </div>
        </div>
      )}
    </div>
  )
}

import { useState } from 'react'