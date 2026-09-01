'use client'

import { ReactNode } from 'react'
import { DashboardLayout } from '@/components/dashboard-layout'

export default function DashboardRootLayout({
  children,
}: {
  children: ReactNode
}) {
  return (
    <DashboardLayout>
      {children}
    </DashboardLayout>
  )
}