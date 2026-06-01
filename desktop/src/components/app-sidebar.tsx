import { NavLink } from "react-router-dom"
import {
  Cable,
  FolderSync,
  GitBranch,
  LayoutDashboard,
  Server,
  Settings,
  Terminal,
  Zap,
} from "lucide-react"
import type { LucideIcon } from "lucide-react"

import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarRail,
} from "@/components/ui/sidebar"

export interface NavItem {
  to: string
  label: string
  icon: LucideIcon
  end?: boolean
}

/** Single source of truth for the primary nav (shared with the site header). */
export const navItems: NavItem[] = [
  { to: "/", label: "仪表盘", icon: LayoutDashboard, end: true },
  { to: "/hosts", label: "主机", icon: Server },
  { to: "/tunnels", label: "端口转发", icon: Cable },
  { to: "/mounts", label: "目录挂载", icon: FolderSync },
  { to: "/mirror", label: "同步镜像", icon: GitBranch },
  { to: "/ai-proxy", label: "AI 代理", icon: Zap },
  { to: "/settings", label: "设置", icon: Settings },
]

export function AppSidebar({
  ...props
}: React.ComponentProps<typeof Sidebar>) {
  return (
    <Sidebar variant="inset" collapsible="icon" {...props}>
      <SidebarHeader>
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton size="lg" asChild>
              <NavLink to="/">
                <div className="flex aspect-square size-8 items-center justify-center rounded-lg bg-primary text-primary-foreground">
                  <Terminal className="size-4" />
                </div>
                <div className="grid flex-1 text-left text-sm leading-tight">
                  <span className="truncate font-semibold">远程开发</span>
                  <span className="truncate text-xs text-muted-foreground">
                    管理器
                  </span>
                </div>
              </NavLink>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarHeader>

      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupLabel>功能</SidebarGroupLabel>
          <SidebarMenu>
            {navItems.map((item) => (
              <SidebarMenuItem key={item.to}>
                <NavLink to={item.to} end={item.end}>
                  {({ isActive }) => (
                    <SidebarMenuButton
                      asChild
                      isActive={isActive}
                      tooltip={item.label}
                    >
                      <span>
                        <item.icon />
                        <span>{item.label}</span>
                      </span>
                    </SidebarMenuButton>
                  )}
                </NavLink>
              </SidebarMenuItem>
            ))}
          </SidebarMenu>
        </SidebarGroup>
      </SidebarContent>

      <SidebarFooter>
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton
              size="sm"
              className="text-muted-foreground"
              tooltip="rdm desktop v0.1.0"
            >
              <span className="grid flex-1 text-left leading-tight">
                <span className="truncate font-medium">rdm 桌面版</span>
                <span className="truncate text-xs">v0.1.0</span>
              </span>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarFooter>
      <SidebarRail />
    </Sidebar>
  )
}
