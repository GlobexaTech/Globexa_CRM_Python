'use client'

import { useState, useEffect } from 'react'
import { User, Bell, Shield, Palette, Globe, Key, Save, Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Separator } from '@/components/ui/separator'
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'
import { Switch } from '@/components/ui/switch'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { useAuth } from '@/lib/auth-context'
import { api, User as UserType } from '@/lib/api'
import { toast } from 'sonner'

const initialProfileData = {
  full_name: '',
  phone: '',
  timezone: 'UTC',
  locale: 'en',
  avatar_url: '',
}

const initialSecurityData = {
  current_password: '',
  new_password: '',
  confirm_password: '',
}

export default function SettingsPage() {
  const { user, tenant, refreshUser } = useAuth()
  const [activeTab, setActiveTab] = useState<'profile' | 'security' | 'notifications' | 'appearance' | 'tenant'>('profile')
  const handleTabChange = (value: string) => {
    setActiveTab(value as 'profile' | 'security' | 'notifications' | 'appearance' | 'tenant')
  }
  const [isSaving, setIsSaving] = useState(false)
  const [profileData, setProfileData] = useState(initialProfileData)
  const [securityData, setSecurityData] = useState(initialSecurityData)
  const [notifications, setNotifications] = useState({
    email_leads: true,
    email_deals: true,
    email_tasks: true,
    email_campaigns: false,
    push_enabled: true,
  })
  const [appearance, setAppearance] = useState({
    theme: 'system',
    density: 'comfortable',
    language: 'en',
  })

  useEffect(() => {
    if (user) {
      setProfileData({
        full_name: user.full_name || '',
        phone: user.phone || '',
        timezone: user.timezone || 'UTC',
        locale: user.locale || 'en',
        avatar_url: user.avatar_url || '',
      })
    }
  }, [user])

  const handleProfileSave = async (e: React.FormEvent) => {
    e.preventDefault()
    setIsSaving(true)
    try {
      await api.updateCurrentUser(profileData)
      await refreshUser()
      toast.success('Profile updated')
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to update profile')
    } finally {
      setIsSaving(false)
    }
  }

  const handleSecuritySave = async (e: React.FormEvent) => {
    e.preventDefault()
    if (securityData.new_password !== securityData.confirm_password) {
      toast.error('Passwords do not match')
      return
    }
    if (securityData.new_password.length < 8) {
      toast.error('Password must be at least 8 characters')
      return
    }
    setIsSaving(true)
    try {
      // API doesn't have password change endpoint yet
      toast.error('Password change not implemented in API yet')
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to change password')
    } finally {
      setIsSaving(false)
    }
  }

  const handleNotificationsChange = (key: string, value: boolean) => {
    setNotifications((prev) => ({ ...prev, [key]: value }))
  }

  const handleAppearanceChange = (key: string, value: string) => {
    setAppearance((prev) => ({ ...prev, [key]: value }))
  }

  return (
    <div className="flex h-screen bg-background">
      <div className="flex-1 overflow-y-auto p-6 lg:p-8 max-w-4xl mx-auto">
        <div className="mb-8">
          <h1 className="text-3xl font-bold tracking-tight">Settings</h1>
          <p className="text-muted-foreground mt-1">Manage your account preferences and tenant settings</p>
        </div>

        <Tabs value={activeTab} onValueChange={handleTabChange} className="w-full">
          <TabsList className="grid w-full grid-cols-5">
            <TabsTrigger value="profile"><User className="mr-2 h-4 w-4" />Profile</TabsTrigger>
            <TabsTrigger value="security"><Shield className="mr-2 h-4 w-4" />Security</TabsTrigger>
            <TabsTrigger value="notifications"><Bell className="mr-2 h-4 w-4" />Notifications</TabsTrigger>
            <TabsTrigger value="appearance"><Palette className="mr-2 h-4 w-4" />Appearance</TabsTrigger>
            {tenant && <TabsTrigger value="tenant"><Globe className="mr-2 h-4 w-4" />Tenant</TabsTrigger>}
          </TabsList>

          <TabsContent value="profile" className="space-y-6 mt-6">
            <Card>
              <CardHeader>
                <div className="flex items-center justify-between">
                  <div>
                    <CardTitle>Profile Information</CardTitle>
                    <p className="text-sm text-muted-foreground">Update your personal information</p>
                  </div>
                  <Avatar className="h-20 w-20">
                    <AvatarImage src={profileData.avatar_url || ''} alt={profileData.full_name || ''} />
                    <AvatarFallback className="text-2xl">
                      {profileData.full_name?.charAt(0).toUpperCase() || user?.full_name?.charAt(0).toUpperCase() || 'U'}
                    </AvatarFallback>
                  </Avatar>
                </div>
              </CardHeader>
              <CardContent>
                <form onSubmit={handleProfileSave} className="space-y-4">
                  <div className="grid gap-4 sm:grid-cols-2">
                    <div className="sm:col-span-2">
                      <Label htmlFor="full_name">Full Name</Label>
                      <Input
                        id="full_name"
                        name="full_name"
                        value={profileData.full_name}
                        onChange={(e) => setProfileData({ ...profileData, full_name: e.target.value })}
                        placeholder="John Doe"
                      />
                    </div>
                    <div>
                      <Label htmlFor="phone">Phone</Label>
                      <Input
                        id="phone"
                        name="phone"
                        value={profileData.phone}
                        onChange={(e) => setProfileData({ ...profileData, phone: e.target.value })}
                        placeholder="+1 555-123-4567"
                      />
                    </div>
                    <div>
                      <Label htmlFor="avatar_url">Avatar URL</Label>
                      <Input
                        id="avatar_url"
                        name="avatar_url"
                        value={profileData.avatar_url}
                        onChange={(e) => setProfileData({ ...profileData, avatar_url: e.target.value })}
                        placeholder="https://example.com/avatar.png"
                      />
                    </div>
                    <div>
                      <Label htmlFor="timezone">Timezone</Label>
                      <Select value={profileData.timezone} onValueChange={(v) => setProfileData({ ...profileData, timezone: v })}>
                        <SelectTrigger><SelectValue /></SelectTrigger>
                        <SelectContent>
                          <SelectItem value="UTC">UTC</SelectItem>
                          <SelectItem value="America/New_York">Eastern Time</SelectItem>
                          <SelectItem value="America/Chicago">Central Time</SelectItem>
                          <SelectItem value="America/Denver">Mountain Time</SelectItem>
                          <SelectItem value="America/Los_Angeles">Pacific Time</SelectItem>
                          <SelectItem value="Europe/London">London</SelectItem>
                          <SelectItem value="Europe/Paris">Paris</SelectItem>
                          <SelectItem value="Asia/Tokyo">Tokyo</SelectItem>
                          <SelectItem value="Asia/Singapore">Singapore</SelectItem>
                          <SelectItem value="Australia/Sydney">Sydney</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                    <div>
                      <Label htmlFor="locale">Language</Label>
                      <Select value={profileData.locale} onValueChange={(v) => setProfileData({ ...profileData, locale: v })}>
                        <SelectTrigger><SelectValue /></SelectTrigger>
                        <SelectContent>
                          <SelectItem value="en">English</SelectItem>
                          <SelectItem value="es">Spanish</SelectItem>
                          <SelectItem value="fr">French</SelectItem>
                          <SelectItem value="de">German</SelectItem>
                          <SelectItem value="pt">Portuguese</SelectItem>
                          <SelectItem value="zh">Chinese</SelectItem>
                          <SelectItem value="ja">Japanese</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                  </div>
                  <Button type="submit" disabled={isSaving}>
                    <Save className="mr-2 h-4 w-4" />
                    {isSaving ? 'Saving...' : 'Save Changes'}
                  </Button>
                </form>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Account Information</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <dl className="grid gap-4 sm:grid-cols-2">
                  <div>
                    <dt className="text-sm text-muted-foreground">Email</dt>
                    <dd className="font-medium">{user?.email}</dd>
                  </div>
                  <div>
                    <dt className="text-sm text-muted-foreground">Role</dt>
                    <dd className="font-medium capitalize">{user?.is_superuser ? 'Super Admin' : 'User'}</dd>
                  </div>
                  <div>
                    <dt className="text-sm text-muted-foreground">Status</dt>
                    <dd className="font-medium">{user?.is_active ? 'Active' : 'Inactive'}</dd>
                  </div>
                  <div>
                    <dt className="text-sm text-muted-foreground">Email Verified</dt>
                    <dd className="font-medium">{user?.email_verified ? 'Yes' : 'No'}</dd>
                  </div>
                  <div>
                    <dt className="text-sm text-muted-foreground">Member Since</dt>
                    <dd className="font-medium">{user?.created_at ? new Date(user.created_at).toLocaleDateString() : 'Unknown'}</dd>
                  </div>
                  <div>
                    <dt className="text-sm text-muted-foreground">Last Login</dt>
                    <dd className="font-medium">{user?.last_login_at ? new Date(user.last_login_at).toLocaleString() : 'Never'}</dd>
                  </div>
                </dl>
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent value="security" className="space-y-6 mt-6">
            <Card>
              <CardHeader>
                <CardTitle>Change Password</CardTitle>
                <p className="text-sm text-muted-foreground">Update your password to keep your account secure</p>
              </CardHeader>
              <CardContent>
                <form onSubmit={handleSecuritySave} className="space-y-4">
                  <div className="grid gap-4 sm:grid-cols-2">
                    <div className="sm:col-span-2">
                      <Label htmlFor="current_password">Current Password</Label>
                      <Input
                        id="current_password"
                        name="current_password"
                        type="password"
                        value={securityData.current_password}
                        onChange={(e) => setSecurityData({ ...securityData, current_password: e.target.value })}
                        placeholder="Enter current password"
                        required
                      />
                    </div>
                    <div>
                      <Label htmlFor="new_password">New Password</Label>
                      <Input
                        id="new_password"
                        name="new_password"
                        type="password"
                        value={securityData.new_password}
                        onChange={(e) => setSecurityData({ ...securityData, new_password: e.target.value })}
                        placeholder="Min 8 characters"
                        required
                      />
                    </div>
                    <div>
                      <Label htmlFor="confirm_password">Confirm New Password</Label>
                      <Input
                        id="confirm_password"
                        name="confirm_password"
                        type="password"
                        value={securityData.confirm_password}
                        onChange={(e) => setSecurityData({ ...securityData, confirm_password: e.target.value })}
                        placeholder="Confirm new password"
                        required
                      />
                    </div>
                  </div>
                  <Button type="submit" disabled={isSaving}>
                    <Key className="mr-2 h-4 w-4" />
                    {isSaving ? 'Saving...' : 'Update Password'}
                  </Button>
                </form>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Two-Factor Authentication</CardTitle>
                <p className="text-sm text-muted-foreground">Add an extra layer of security to your account</p>
              </CardHeader>
              <CardContent>
                <div className="flex items-center justify-between">
                  <div>
                    <p className="font-medium">Authenticator App</p>
                    <p className="text-sm text-muted-foreground">Use Google Authenticator, Authy, or similar</p>
                  </div>
                  <Button variant="outline">Enable 2FA</Button>
                </div>
              </CardContent>
            </Card>

            <Card className="border-destructive/50">
              <CardHeader>
                <CardTitle className="text-destructive">Danger Zone</CardTitle>
                <p className="text-sm text-muted-foreground">Irreversible actions</p>
              </CardHeader>
              <CardContent>
                <div className="flex items-center justify-between">
                  <div>
                    <p className="font-medium">Delete Account</p>
                    <p className="text-sm text-muted-foreground">Permanently delete your account and all data</p>
                  </div>
                  <Button variant="destructive" onClick={() => { if (confirm('Are you sure? This cannot be undone.')) { /* TODO */ } }}>
                    Delete Account
                  </Button>
                </div>
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent value="notifications" className="space-y-6 mt-6">
            <Card>
              <CardHeader>
                <CardTitle>Email Notifications</CardTitle>
                <p className="text-sm text-muted-foreground">Choose which emails you want to receive</p>
              </CardHeader>
              <CardContent className="space-y-4">
                <NotificationToggle label="New Leads" description="When a new lead is assigned to you" checked={notifications.email_leads} onChange={(v) => handleNotificationsChange('email_leads', v)} />
                <NotificationToggle label="Deal Updates" description="When deals are updated or moved" checked={notifications.email_deals} onChange={(v) => handleNotificationsChange('email_deals', v)} />
                <NotificationToggle label="Task Reminders" description="Daily summary of upcoming tasks" checked={notifications.email_tasks} onChange={(v) => handleNotificationsChange('email_tasks', v)} />
                <NotificationToggle label="Campaign Reports" description="Weekly campaign performance reports" checked={notifications.email_campaigns} onChange={(v) => handleNotificationsChange('email_campaigns', v)} />
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Push Notifications</CardTitle>
                <p className="text-sm text-muted-foreground">Receive browser notifications</p>
              </CardHeader>
              <CardContent>
                <NotificationToggle label="Enable Push Notifications" description="Receive real-time updates in your browser" checked={notifications.push_enabled} onChange={(v) => handleNotificationsChange('push_enabled', v)} />
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent value="appearance" className="space-y-6 mt-6">
            <Card>
              <CardHeader>
                <CardTitle>Theme</CardTitle>
                <p className="text-sm text-muted-foreground">Choose your preferred color scheme</p>
              </CardHeader>
              <CardContent>
                <Select value={appearance.theme} onValueChange={(v) => handleAppearanceChange('theme', v)}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="light">Light</SelectItem>
                    <SelectItem value="dark">Dark</SelectItem>
                    <SelectItem value="system">System</SelectItem>
                  </SelectContent>
                </Select>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Display Density</CardTitle>
                <p className="text-sm text-muted-foreground">Adjust spacing and compactness</p>
              </CardHeader>
              <CardContent>
                <Select value={appearance.density} onValueChange={(v) => handleAppearanceChange('density', v)}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="compact">Compact</SelectItem>
                    <SelectItem value="comfortable">Comfortable</SelectItem>
                    <SelectItem value="spacious">Spacious</SelectItem>
                  </SelectContent>
                </Select>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Language</CardTitle>
                <p className="text-sm text-muted-foreground">Interface language</p>
              </CardHeader>
              <CardContent>
                <Select value={appearance.language} onValueChange={(v) => handleAppearanceChange('language', v)}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="en">English</SelectItem>
                    <SelectItem value="es">Spanish</SelectItem>
                    <SelectItem value="fr">French</SelectItem>
                    <SelectItem value="de">German</SelectItem>
                    <SelectItem value="pt">Portuguese</SelectItem>
                    <SelectItem value="zh">Chinese</SelectItem>
                    <SelectItem value="ja">Japanese</SelectItem>
                  </SelectContent>
                </Select>
              </CardContent>
            </Card>
          </TabsContent>

          {tenant && (
            <TabsContent value="tenant" className="space-y-6 mt-6">
              <Card>
                <CardHeader>
                  <CardTitle>Tenant Settings</CardTitle>
                  <p className="text-sm text-muted-foreground">Manage your tenant configuration</p>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="grid gap-4 sm:grid-cols-2">
                    <div>
                      <Label>Tenant Name</Label>
                      <Input value={tenant.name} disabled />
                    </div>
                    <div>
                      <Label>Slug</Label>
                      <Input value={tenant.slug} disabled />
                    </div>
                    <div>
                      <Label>Domain</Label>
                      <Input value={tenant.domain || 'Not configured'} disabled />
                    </div>
                    <div>
                      <Label>Status</Label>
                      <Input value={tenant.is_active ? 'Active' : 'Inactive'} disabled />
                    </div>
                    <div>
                      <Label>Package</Label>
                      <Input value={tenant.subscription?.package || 'None'} disabled />
                    </div>
                    <div>
                      <Label>Subscription Status</Label>
                      <Input value={tenant.subscription?.status || 'N/A'} disabled />
                    </div>
                  </div>
                </CardContent>
              </Card>
            </TabsContent>
          )}
        </Tabs>
      </div>
    </div>
  )
}

function NotificationToggle({ label, description, checked, onChange }: { label: string; description: string; checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <div className="flex items-center justify-between">
      <div>
        <p className="font-medium">{label}</p>
        <p className="text-sm text-muted-foreground">{description}</p>
      </div>
      <Switch checked={checked} onCheckedChange={onChange} />
    </div>
  )
}