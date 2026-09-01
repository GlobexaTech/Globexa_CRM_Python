'use client'

import { useState } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { useAuth } from '@/lib/auth-context'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '@/components/ui/card'
import { Loader2, Mail, Lock, User, AlertCircle, Building2 } from 'lucide-react'
import { toast } from 'sonner'

export default function RegisterPage() {
  const router = useRouter()
  const { register } = useAuth()
  const [formData, setFormData] = useState({
    email: '',
    password: '',
    confirmPassword: '',
    fullName: '',
    tenantName: '',
    tenantSlug: '',
  })
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState('')

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setFormData({ ...formData, [e.target.name]: e.target.value })
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')

    if (formData.password !== formData.confirmPassword) {
      setError('Passwords do not match')
      toast.error('Passwords do not match')
      return
    }

    if (formData.password.length < 8) {
      setError('Password must be at least 8 characters')
      toast.error('Password must be at least 8 characters')
      return
    }

    setIsLoading(true)

    try {
      await register({
        email: formData.email,
        password: formData.password,
        full_name: formData.fullName,
        tenant_name: formData.tenantName || undefined,
        tenant_slug: formData.tenantSlug || undefined,
      })
      toast.success('Account created successfully!')
      router.push('/dashboard')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Registration failed')
      toast.error(err instanceof Error ? err.message : 'Registration failed')
    } finally {
      setIsLoading(false)
    }
  }

  // Auto-generate slug from tenant name
  const handleTenantNameChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value
    setFormData({
      ...formData,
      tenantName: value,
      tenantSlug: value.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/(^-|-$)/g, ''),
    })
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-muted/50 px-4 py-12">
      <Card className="w-full max-w-md">
        <CardHeader className="text-center">
          <CardTitle className="text-2xl font-bold">Create your account</CardTitle>
          <CardDescription>Start managing your sales pipeline with Globexa CRM</CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
            {error && (
              <div className="flex items-center gap-2 text-sm text-destructive bg-destructive/10 p-3 rounded-lg">
                <AlertCircle className="h-4 w-4" />
                <span>{error}</span>
              </div>
            )}

            <div className="space-y-2">
              <Label htmlFor="fullName">Full Name</Label>
              <div className="relative">
                <User className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                <Input
                  id="fullName"
                  name="fullName"
                  type="text"
                  placeholder="John Doe"
                  value={formData.fullName}
                  onChange={handleChange}
                  className="pl-10"
                  required
                  disabled={isLoading}
                />
              </div>
            </div>

            <div className="space-y-2">
              <Label htmlFor="email">Email</Label>
              <div className="relative">
                <Mail className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                <Input
                  id="email"
                  name="email"
                  type="email"
                  placeholder="you@company.com"
                  value={formData.email}
                  onChange={handleChange}
                  className="pl-10"
                  required
                  disabled={isLoading}
                />
              </div>
            </div>

            <div className="space-y-2">
              <Label htmlFor="password">Password</Label>
              <div className="relative">
                <Lock className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                <Input
                  id="password"
                  name="password"
                  type="password"
                  placeholder="•••••••• (min 8 chars)"
                  value={formData.password}
                  onChange={handleChange}
                  className="pl-10"
                  required
                  disabled={isLoading}
                />
              </div>
            </div>

            <div className="space-y-2">
              <Label htmlFor="confirmPassword">Confirm Password</Label>
              <div className="relative">
                <Lock className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                <Input
                  id="confirmPassword"
                  name="confirmPassword"
                  type="password"
                  placeholder="••••••••"
                  value={formData.confirmPassword}
                  onChange={handleChange}
                  className="pl-10"
                  required
                  disabled={isLoading}
                />
              </div>
            </div>

            <div className="border-t pt-6 space-y-4">
              <h3 className="text-sm font-medium text-muted-foreground">Tenant Setup (Optional)</h3>
              <p className="text-xs text-muted-foreground">
                A tenant will be created automatically. Customize it here or use defaults.
              </p>

              <div className="space-y-2">
                <Label htmlFor="tenantName">Tenant Name</Label>
                <div className="relative">
                  <Building2 className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                  <Input
                    id="tenantName"
                    name="tenantName"
                    type="text"
                    placeholder="Acme Inc"
                    value={formData.tenantName}
                    onChange={handleTenantNameChange}
                    className="pl-10"
                    disabled={isLoading}
                  />
                </div>
              </div>

              <div className="space-y-2">
                <Label htmlFor="tenantSlug">Tenant Slug</Label>
                <div className="relative">
                  <Building2 className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                  <Input
                    id="tenantSlug"
                    name="tenantSlug"
                    type="text"
                    placeholder="acme-inc"
                    value={formData.tenantSlug}
                    onChange={handleChange}
                    className="pl-10"
                    disabled={isLoading}
                  />
                </div>
                <p className="text-xs text-muted-foreground">
                  Used for subdomain: {formData.tenantSlug || 'your-slug'}.globexa.app
                </p>
              </div>
            </div>

            <Button type="submit" className="w-full" size="lg" disabled={isLoading}>
              {isLoading ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Creating account...
                </>
              ) : (
                'Create account'
              )}
            </Button>
          </form>
        </CardContent>
        <CardFooter className="flex flex-col space-y-4">
          <p className="text-center text-sm text-muted-foreground">
            Already have an account?{' '}
            <Link href="/login" className="text-primary hover:underline font-medium">
              Sign in
            </Link>
          </p>
        </CardFooter>
      </Card>
    </div>
  )
}