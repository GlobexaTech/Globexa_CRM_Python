import { ReactNode, useState } from 'react'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { cn } from '@/lib/utils'
import {
  Sidebar,
  SidebarProvider,
  SidebarInset,
  SidebarContent,
  SidebarGroup,
  SidebarGroupLabel,
  SidebarMenu,
  SidebarMenuItem,
  SidebarMenuButton,
  SidebarHeader,
} from '@/components/ui/sidebar'
import {
  LayoutDashboard,
  Users,
  Building2,
  Target,
  GitBranch,
  Briefcase,
  Settings,
  ChevronLeft,
  ChevronRight,
  LogOut,
  Menu,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Separator } from '@/components/ui/separator'
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from '@/components/ui/dropdown-menu'
import { useAuth } from '@/lib/auth-context'
import { Toaster } from '@/components/ui/sonner'

const navigation = [
  { name: 'Dashboard', href: '/dashboard', icon: LayoutDashboard },
  { name: 'Companies', href: '/dashboard/companies', icon: Building2 },
  { name: 'Contacts', href: '/dashboard/contacts', icon: Users },
  { name: 'Leads', href: '/dashboard/leads', icon: Target },
  { name: 'Pipelines', href: '/dashboard/pipelines', icon: GitBranch },
  { name: 'Deals', href: '/dashboard/deals', icon: Briefcase },
  { name: 'Tenants', href: '/dashboard/tenants', icon: Building2 },
  { name: 'Settings', href: '/dashboard/settings', icon: Settings },
]

export function DashboardLayout({ children }: { children: ReactNode }) {
  const pathname = usePathname()
  const [collapsed, setCollapsed] = useState(false)
  const [mobileOpen, setMobileOpen] = useState(false)
  const { user, tenant, tenants, switchTenant, logout } = useAuth()

  return (
    <SidebarProvider open={!collapsed} onOpenChange={(open) => setCollapsed(!open)}>
      <Sidebar>
        <SidebarContent className="h-screen">
          <SidebarHeader className="p-4">
            <Link href="/dashboard" className="flex items-center gap-2">
              <div className="h-8 w-8 rounded-lg bg-primary flex items-center justify-center">
                <Target className="h-5 w-5 text-primary-foreground" />
              </div>
              <span className="font-bold text-lg hidden lg:block">Globexa CRM</span>
            </Link>
          </SidebarHeader>

          <SidebarGroup>
            <SidebarGroupLabel>Navigation</SidebarGroupLabel>
            <SidebarMenu>
              {navigation.map((item) => (
                <SidebarMenuItem key={item.name}>
                  <SidebarMenuButton asChild>
                    <Link
                      href={item.href}
                      className={cn(
                        pathname === item.href && 'bg-sidebar-accent text-sidebar-accent-foreground'
                      )}
                    >
                      <item.icon className="h-4 w-4" />
                      <span>{item.name}</span>
                    </Link>
                  </SidebarMenuButton>
                </SidebarMenuItem>
              ))}
            </SidebarMenu>
          </SidebarGroup>

          <Separator className="mx-2" />

          <SidebarGroup>
            <SidebarGroupLabel>Account</SidebarGroupLabel>
            <SidebarMenu>
              <SidebarMenuItem>
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <SidebarMenuButton className="w-full justify-start gap-3">
                      <Avatar className="h-8 w-8">
                        <AvatarImage src={user?.avatar_url || ''} alt={user?.full_name || ''} />
                        <AvatarFallback>
                          {user?.full_name?.charAt(0).toUpperCase() || 'U'}
                        </AvatarFallback>
                      </Avatar>
                      <div className="flex-1 text-left min-w-0">
                        <p className="text-sm font-medium truncate">{user?.full_name || 'User'}</p>
                        <p className="text-xs text-muted-foreground truncate">{tenant?.name || 'No tenant'}</p>
                      </div>
                      <ChevronRight className="h-4 w-4" />
                    </SidebarMenuButton>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent className="w-56" align="end" forceMount>
                    <div className="px-2 py-1">
                      <p className="text-xs font-medium text-muted-foreground">Switch Tenant</p>
                    </div>
                    {tenants.map((t) => (
                      <DropdownMenuItem
                        key={t.id}
                        onClick={() => switchTenant(t.id)}
                        className={cn(t.id === tenant?.id && 'bg-sidebar-accent')}
                      >
                        <div className="flex items-center justify-between">
                          <span>{t.name}</span>
                          {t.is_default && (
                            <span className="text-xs text-muted-foreground">Default</span>
                          )}
                        </div>
                      </DropdownMenuItem>
                    ))}
                    {tenants.length === 0 && (
                      <DropdownMenuItem className="text-muted-foreground">
                        No other tenants
                      </DropdownMenuItem>
                    )}
                    <DropdownMenuItem
                      onClick={logout}
                      className="text-destructive focus:text-destructive"
                    >
                      <LogOut className="mr-2 h-4 w-4" />
                      Log out
                    </DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
              </SidebarMenuItem>
            </SidebarMenu>
          </SidebarGroup>
        </SidebarContent>
      </Sidebar>
      <SidebarInset>
        {children}
      </SidebarInset>
    </SidebarProvider>
  )
}