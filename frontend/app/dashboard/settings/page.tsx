"use client"

import { useState } from "react"
import { useRouter } from "next/navigation"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Switch } from "@/components/ui/switch"
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog"
import { apiPost } from "@/lib/api"
import {
  Shield,
  Bell,
  Globe,
  Moon,
  Trash2,
  AlertTriangle,
  LogOut,
} from "lucide-react"

export default function SettingsPage() {
  const router = useRouter()
  const [settings, setSettings] = useState({
    emailNotifications: true,
    pushNotifications: false,
    weeklyDigest: true,
    darkMode: true,
    publicProfile: false,
    twoFactorAuth: false,
  })
  const [isLoggingOutAll, setIsLoggingOutAll] = useState(false)

  // Phase 26 H2 — POST /v1/auth/logout-all. Backend revokes every
  // sessions row for the calling user (this device too, per CONTEXT
  // D-04) and writes an auth_events audit row. Cookie is cleared on
  // the response; navigate to /login on success.
  const handleLogoutAll = async () => {
    setIsLoggingOutAll(true)
    try {
      await apiPost("/api/v1/auth/logout-all", {})
      router.push("/login")
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Couldn't log out everywhere"
      toast.error(msg)
      setIsLoggingOutAll(false)
    }
  }

  return (
    <div>
      <div className="mb-6 sm:mb-8">
        <h1 className="text-2xl font-bold text-foreground sm:text-3xl">Settings</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Manage your account preferences
        </p>
      </div>

      <div className="max-w-2xl space-y-6">
        {/* Notifications */}
        <div className="rounded-xl border border-border/50 bg-card/30 p-5 backdrop-blur-sm sm:p-6">
          <div className="mb-4 flex items-center gap-2">
            <Bell className="h-5 w-5 text-primary" />
            <h2 className="font-semibold text-foreground">Notifications</h2>
          </div>
          
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-foreground">Email Notifications</p>
                <p className="text-xs text-muted-foreground">Receive email updates about your agents</p>
              </div>
              <Switch
                checked={settings.emailNotifications}
                onCheckedChange={(v) => setSettings({ ...settings, emailNotifications: v })}
              />
            </div>
            
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-foreground">Push Notifications</p>
                <p className="text-xs text-muted-foreground">Get push notifications on your devices</p>
              </div>
              <Switch
                checked={settings.pushNotifications}
                onCheckedChange={(v) => setSettings({ ...settings, pushNotifications: v })}
              />
            </div>

            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-foreground">Weekly Digest</p>
                <p className="text-xs text-muted-foreground">Weekly summary of agent activity</p>
              </div>
              <Switch
                checked={settings.weeklyDigest}
                onCheckedChange={(v) => setSettings({ ...settings, weeklyDigest: v })}
              />
            </div>
          </div>
        </div>

        {/* Appearance */}
        <div className="rounded-xl border border-border/50 bg-card/30 p-5 backdrop-blur-sm sm:p-6">
          <div className="mb-4 flex items-center gap-2">
            <Moon className="h-5 w-5 text-primary" />
            <h2 className="font-semibold text-foreground">Appearance</h2>
          </div>
          
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-foreground">Dark Mode</p>
              <p className="text-xs text-muted-foreground">Use dark theme across the platform</p>
            </div>
            <Switch
              checked={settings.darkMode}
              onCheckedChange={(v) => setSettings({ ...settings, darkMode: v })}
            />
          </div>
        </div>

        {/* Privacy */}
        <div className="rounded-xl border border-border/50 bg-card/30 p-5 backdrop-blur-sm sm:p-6">
          <div className="mb-4 flex items-center gap-2">
            <Globe className="h-5 w-5 text-primary" />
            <h2 className="font-semibold text-foreground">Privacy</h2>
          </div>
          
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-foreground">Public Profile</p>
              <p className="text-xs text-muted-foreground">Make your profile visible to others</p>
            </div>
            <Switch
              checked={settings.publicProfile}
              onCheckedChange={(v) => setSettings({ ...settings, publicProfile: v })}
            />
          </div>
        </div>

        {/* Security */}
        <div className="rounded-xl border border-border/50 bg-card/30 p-5 backdrop-blur-sm sm:p-6">
          <div className="mb-4 flex items-center gap-2">
            <Shield className="h-5 w-5 text-primary" />
            <h2 className="font-semibold text-foreground">Security</h2>
          </div>
          
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-foreground">Two-Factor Authentication</p>
                <p className="text-xs text-muted-foreground">Add an extra layer of security</p>
              </div>
              <Switch
                checked={settings.twoFactorAuth}
                onCheckedChange={(v) => setSettings({ ...settings, twoFactorAuth: v })}
              />
            </div>

            <div>
              <label className="mb-1.5 block text-sm text-muted-foreground">Change Password</label>
              <div className="flex gap-3">
                <Input type="password" placeholder="New password" className="flex-1 bg-background/50" />
                <Button variant="outline">Update</Button>
              </div>
            </div>

            {/* Phase 26 H2 — log out of every device for this user. */}
            <div className="border-t border-border/50 pt-4">
              <p className="mb-2 text-sm font-medium text-foreground">Sign out everywhere</p>
              <p className="mb-3 text-xs text-muted-foreground">
                Revoke every active session for your account, including this one.
                Useful if you suspect a device was compromised. Running agents keep running.
              </p>
              <AlertDialog>
                <AlertDialogTrigger asChild>
                  <Button variant="destructive" className="gap-2" disabled={isLoggingOutAll}>
                    <LogOut className="h-4 w-4" />
                    Log out everywhere
                  </Button>
                </AlertDialogTrigger>
                <AlertDialogContent>
                  <AlertDialogHeader>
                    <AlertDialogTitle>Log out everywhere?</AlertDialogTitle>
                    <AlertDialogDescription>
                      You will be signed out on every device, including this one.
                      Running agents keep running.
                    </AlertDialogDescription>
                  </AlertDialogHeader>
                  <AlertDialogFooter>
                    <AlertDialogCancel disabled={isLoggingOutAll}>Cancel</AlertDialogCancel>
                    <AlertDialogAction
                      onClick={handleLogoutAll}
                      disabled={isLoggingOutAll}
                      className="bg-destructive text-white hover:bg-destructive/90"
                    >
                      {isLoggingOutAll ? "Signing out…" : "Log out everywhere"}
                    </AlertDialogAction>
                  </AlertDialogFooter>
                </AlertDialogContent>
              </AlertDialog>
            </div>
          </div>
        </div>

        {/* Danger Zone */}
        <div className="rounded-xl border border-destructive/30 bg-destructive/5 p-5 sm:p-6">
          <div className="mb-4 flex items-center gap-2">
            <AlertTriangle className="h-5 w-5 text-destructive" />
            <h2 className="font-semibold text-destructive">Danger Zone</h2>
          </div>
          
          <p className="mb-4 text-sm text-muted-foreground">
            Once you delete your account, there is no going back. Please be certain.
          </p>
          
          <Button variant="destructive" className="gap-2">
            <Trash2 className="h-4 w-4" />
            Delete Account
          </Button>
        </div>
      </div>
    </div>
  )
}
