"use client"

import { useState } from "react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar"
import { User, Mail, Building2, Globe, Camera, Check } from "lucide-react"

export default function ProfilePage() {
  const [saved, setSaved] = useState(false)
  const [profile, setProfile] = useState({
    name: "Alex Chen",
    email: "alex@example.com",
    company: "Acme Inc",
    website: "https://alexchen.dev",
    bio: "Building autonomous agents for the future.",
  })

  const handleSave = () => {
    setSaved(true)
    setTimeout(() => setSaved(false), 2000)
  }

  return (
    <div>
      <div className="mb-6 sm:mb-8">
        <h1 className="text-2xl font-bold text-foreground sm:text-3xl">Profile</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Manage your personal information
        </p>
      </div>

      <div className="max-w-2xl space-y-6">
        {/* Avatar Section */}
        <div className="rounded-xl border border-border/50 bg-card/30 p-5 backdrop-blur-sm sm:p-6">
          <h2 className="mb-4 font-semibold text-foreground">Profile Picture</h2>
          <div className="flex items-center gap-4">
            <div className="relative">
              <Avatar className="h-20 w-20">
                <AvatarImage src="" />
                <AvatarFallback className="bg-primary text-lg text-primary-foreground">
                  AC
                </AvatarFallback>
              </Avatar>
              <button className="absolute bottom-0 right-0 flex h-8 w-8 items-center justify-center rounded-full border border-border bg-background text-muted-foreground hover:text-foreground">
                <Camera className="h-4 w-4" />
              </button>
            </div>
            <div>
              <p className="text-sm text-muted-foreground">
                JPG, GIF or PNG. Max size 2MB.
              </p>
              <Button variant="outline" size="sm" className="mt-2">
                Upload Image
              </Button>
            </div>
          </div>
        </div>

        {/* Personal Info */}
        <div className="rounded-xl border border-border/50 bg-card/30 p-5 backdrop-blur-sm sm:p-6">
          <h2 className="mb-4 font-semibold text-foreground">Personal Information</h2>
          <div className="space-y-4">
            <div>
              <label className="mb-1.5 flex items-center gap-2 text-sm text-muted-foreground">
                <User className="h-4 w-4" />
                Full Name
              </label>
              <Input
                value={profile.name}
                onChange={(e) => setProfile({ ...profile, name: e.target.value })}
                className="bg-background/50"
              />
            </div>

            <div>
              <label className="mb-1.5 flex items-center gap-2 text-sm text-muted-foreground">
                <Mail className="h-4 w-4" />
                Email Address
              </label>
              <Input
                type="email"
                value={profile.email}
                onChange={(e) => setProfile({ ...profile, email: e.target.value })}
                className="bg-background/50"
              />
            </div>

            <div>
              <label className="mb-1.5 flex items-center gap-2 text-sm text-muted-foreground">
                <Building2 className="h-4 w-4" />
                Company
              </label>
              <Input
                value={profile.company}
                onChange={(e) => setProfile({ ...profile, company: e.target.value })}
                placeholder="Your company name"
                className="bg-background/50"
              />
            </div>

            <div>
              <label className="mb-1.5 flex items-center gap-2 text-sm text-muted-foreground">
                <Globe className="h-4 w-4" />
                Website
              </label>
              <Input
                type="url"
                value={profile.website}
                onChange={(e) => setProfile({ ...profile, website: e.target.value })}
                placeholder="https://yourwebsite.com"
                className="bg-background/50"
              />
            </div>

            <div>
              <label className="mb-1.5 block text-sm text-muted-foreground">Bio</label>
              <textarea
                value={profile.bio}
                onChange={(e) => setProfile({ ...profile, bio: e.target.value })}
                rows={3}
                className="w-full resize-none rounded-md border border-border/50 bg-background/50 px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary"
                placeholder="Tell us about yourself..."
              />
            </div>
          </div>
        </div>

        {/* Save Button */}
        <div className="flex justify-end">
          <Button 
            onClick={handleSave}
            className="gap-2 bg-primary text-primary-foreground"
          >
            {saved ? (
              <>
                <Check className="h-4 w-4" />
                Saved!
              </>
            ) : (
              "Save Changes"
            )}
          </Button>
        </div>
      </div>
    </div>
  )
}
