import { User, Globe, Bell, Shield, Edit2, Heart, RotateCcw } from "lucide-react";
import { useNavigate } from "react-router-dom";
import AppLayout from "@/components/AppLayout";
import { clearOnboarding, getOnboardingState } from "@/lib/personas";

const Profile = () => {
  const navigate = useNavigate();
  const onboarding = getOnboardingState();

  const handleResetOnboarding = () => {
    clearOnboarding();
    navigate("/onboarding");
  };

  return (
    <AppLayout>
      <div className="mb-12">
        <h1 className="font-display text-5xl font-bold tracking-tight lg:text-7xl">
          <em className="text-primary">Profile</em>
        </h1>
        <div className="rule-thick mt-6 mb-8 max-w-32" />
        <p className="max-w-lg text-lg text-muted-foreground">
          Manage your health profile and preferences
        </p>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* Profile card */}
        <div className="rounded-lg bg-primary p-8 text-center text-primary-foreground">
          <div className="relative mx-auto mb-4 flex h-24 w-24 items-center justify-center rounded-full bg-primary-foreground/20">
            <span className="font-display text-3xl font-bold">AP</span>
            <button className="absolute -right-1 -bottom-1 flex h-8 w-8 items-center justify-center rounded-full bg-primary-foreground text-primary shadow-md">
              <Edit2 size={12} strokeWidth={1.5} />
            </button>
          </div>
          <h2 className="font-display text-2xl font-bold">Amma Patel</h2>
          <p className="mt-1 font-mono text-[10px] uppercase tracking-widest opacity-70">
            Patient · Age 72
          </p>
          <div className="mt-4 flex justify-center gap-2">
            <span className="rounded-full bg-primary-foreground/20 px-3 py-1 font-mono text-xs uppercase tracking-widest">
              Hindi
            </span>
            <span className="rounded-full border border-primary-foreground/30 px-3 py-1 font-mono text-xs uppercase tracking-widest opacity-70">
              English
            </span>
          </div>
        </div>

        {/* Details */}
        <div className="rounded-lg border border-border bg-card p-8 lg:col-span-2">
          <h2 className="mb-6 font-display text-2xl font-bold tracking-tight">Health Information</h2>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            {[
              { icon: Heart, label: "Conditions", value: "Type 2 Diabetes, Hypertension" },
              { icon: Globe, label: "Primary Language", value: "Hindi" },
              { icon: User, label: "Emergency Contact", value: "Priya Patel (Daughter)" },
              { icon: Shield, label: "Blood Type", value: "A+" },
              { icon: Bell, label: "Reminder Preference", value: "Voice + Push" },
              { icon: User, label: "Primary Doctor", value: "Dr. Sharma (Cardiology)" },
            ].map((item, i) => (
              <div
                key={i}
                className="flex items-start gap-4 rounded-md border border-border p-4"
              >
                <div className="rounded-full bg-primary/10 p-2 text-primary">
                  <item.icon size={16} strokeWidth={1.5} />
                </div>
                <div>
                  <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">{item.label}</p>
                  <p className="mt-1 text-sm font-semibold">{item.value}</p>
                </div>
              </div>
            ))}
          </div>

          <div className="mt-8 flex gap-3">
            <button className="rounded-md bg-primary px-8 py-3 font-mono text-sm uppercase tracking-widest text-primary-foreground shadow-md transition-all hover:shadow-lg">
              Edit Profile →
            </button>
            <button className="rounded-md border-2 border-border px-6 py-3 font-mono text-sm uppercase tracking-widest transition-colors hover:bg-secondary">
              Settings
            </button>
            <button
              onClick={handleResetOnboarding}
              className="inline-flex items-center gap-2 rounded-md border-2 border-destructive/30 px-6 py-3 font-mono text-sm uppercase tracking-widest text-destructive transition-colors hover:bg-destructive/10"
            >
              <RotateCcw size={14} /> Reset Companion
            </button>
          </div>

          {onboarding.persona && (
            <div className="mt-6 flex items-center gap-4 rounded-md border border-border p-4">
              <img
                src={onboarding.persona.avatar}
                alt={onboarding.persona.name}
                className="h-12 w-12 rounded-full border-2 border-primary/20 object-cover"
              />
              <div>
                <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">Current Companion</p>
                <p className="mt-0.5 text-sm font-semibold">{onboarding.persona.name} · {onboarding.persona.language}</p>
              </div>
            </div>
          )}
        </div>
      </div>
    </AppLayout>
  );
};

export default Profile;
