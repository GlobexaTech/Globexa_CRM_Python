'use client'

import { useAuth } from '@/lib/auth-context'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Building2, Users, Target, Briefcase, TrendingUp, Plus, ArrowUpRight } from 'lucide-react'
import Link from 'next/link'
import { api } from '@/lib/api'
import { useEffect, useState } from 'react'
import { cn } from '@/lib/utils'

interface DashboardStats {
  companies: number
  contacts: number
  leads: number
  deals: number
  openDealsValue: number
  wonDealsValue: number
}

export default function DashboardPage() {
  const { user, tenant, isLoading: authLoading } = useAuth()
  const [stats, setStats] = useState<DashboardStats | null>(null)
  const [isLoading, setIsLoading] = useState(true)

  useEffect(() => {
    if (!authLoading && tenant) {
      fetchStats()
    }
  }, [authLoading, tenant])

  const fetchStats = async () => {
    try {
      // Fetch counts from API
      const [companies, contacts, leads, deals] = await Promise.all([
        api.listCompanies({ page_size: 1 }),
        api.listContacts({ page_size: 1 }),
        api.listLeads({ page_size: 1 }),
        api.listDeals({ page_size: 1 }),
      ])

      setStats({
        companies: companies.total,
        contacts: contacts.total,
        leads: leads.total,
        deals: deals.total,
        openDealsValue: 0,
        wonDealsValue: 0,
      })
    } catch (error) {
      console.error('Failed to fetch stats:', error)
    } finally {
      setIsLoading(false)
    }
  }

  const statCards = [
    {
      name: 'Companies',
      value: stats?.companies ?? (isLoading ? '—' : 0),
      icon: Building2,
      color: 'bg-blue-500',
      href: '/dashboard/companies',
    },
    {
      name: 'Contacts',
      value: stats?.contacts ?? (isLoading ? '—' : 0),
      icon: Users,
      color: 'bg-green-500',
      href: '/dashboard/contacts',
    },
    {
      name: 'Leads',
      value: stats?.leads ?? (isLoading ? '—' : 0),
      icon: Target,
      color: 'bg-purple-500',
      href: '/dashboard/leads',
    },
    {
      name: 'Deals',
      value: stats?.deals ?? (isLoading ? '—' : 0),
      icon: Briefcase,
      color: 'bg-orange-500',
      href: '/dashboard/deals',
    },
  ]

  if (authLoading) {
    return (
      <div className="flex h-screen items-center justify-center">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent" />
      </div>
    )
  }

  return (
    <div className="flex h-screen bg-background">
      <div className="flex-1 overflow-y-auto p-6 lg:p-8">
        <div className="mb-8">
          <h1 className="text-3xl font-bold tracking-tight">Dashboard</h1>
          <p className="text-muted-foreground mt-1">
            Welcome back, {user?.full_name?.split(' ')[0] || 'User'}! Here's what's happening with your pipeline.
          </p>
        </div>

        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4 mb-8">
          {statCards.map((stat) => (
            <Card key={stat.name}>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium text-muted-foreground">
                  {stat.name}
                </CardTitle>
                <stat.icon className={cn('h-4 w-4', stat.color)} />
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold">{stat.value}</div>
                <p className="text-xs text-muted-foreground">
                  Total {stat.name.toLowerCase()}
                </p>
              </CardContent>
            </Card>
          ))}
        </div>

        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {/* Quick Actions */}
          <Card className="md:col-span-2 lg:col-span-2">
            <CardHeader>
              <CardTitle>Quick Actions</CardTitle>
            </CardHeader>
            <CardContent className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              <Link href="/dashboard/companies" className="flex flex-col items-center justify-center p-4 border rounded-lg hover:bg-accent transition-colors">
                <Building2 className="h-8 w-8 text-primary mb-2" />
                <span className="font-medium">Add Company</span>
                <p className="text-xs text-muted-foreground text-center">Create new company</p>
              </Link>
              <Link href="/dashboard/contacts" className="flex flex-col items-center justify-center p-4 border rounded-lg hover:bg-accent transition-colors">
                <Users className="h-8 w-8 text-green-500 mb-2" />
                <span className="font-medium">Add Contact</span>
                <p className="text-xs text-muted-foreground text-center">Create new contact</p>
              </Link>
              <Link href="/dashboard/leads" className="flex flex-col items-center justify-center p-4 border rounded-lg hover:bg-accent transition-colors">
                <Target className="h-8 w-8 text-purple-500 mb-2" />
                <span className="font-medium">Create Lead</span>
                <p className="text-xs text-muted-foreground text-center">New sales opportunity</p>
              </Link>
              <Link href="/dashboard/deals" className="flex flex-col items-center justify-center p-4 border rounded-lg hover:bg-accent transition-colors">
                <Briefcase className="h-8 w-8 text-orange-500 mb-2" />
                <span className="font-medium">New Deal</span>
                <p className="text-xs text-muted-foreground text-center">Add to pipeline</p>
              </Link>
            </CardContent>
          </Card>

          {/* Tenant Info */}
          <Card>
            <CardHeader>
              <CardTitle>Current Tenant</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div>
                <p className="text-sm text-muted-foreground">Name</p>
                <p className="font-medium">{tenant?.name || 'Not set'}</p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Slug</p>
                <p className="font-medium">{tenant?.slug || 'Not set'}</p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Domain</p>
                <p className="font-medium">{tenant?.domain || 'Not configured'}</p>
              </div>
              <div className="flex items-center gap-2">
                <Badge variant={tenant?.is_active ? 'default' : 'secondary'}>
                  {tenant?.is_active ? 'Active' : 'Inactive'}
                </Badge>
                {tenant?.subscription && (
                  <Badge variant="outline">{tenant.subscription.package}</Badge>
                )}
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  )
}