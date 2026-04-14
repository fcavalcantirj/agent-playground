"use client"

import { useState } from "react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Switch } from "@/components/ui/switch"
import { Shield, Bell, Globe, Moon, Trash2, AlertTriangle } from "lucide-react"

export default function SettingsPage() {
  const [settings, setSettings] = useState({
    emailNotifications: true,
    pushNotifications: false,
    weeklyDigest: true,
    darkMode: true,
    publicProfile: false,
    twoFactorAuth: false,
  })

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
