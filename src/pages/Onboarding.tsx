import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import { Sparkles, ArrowRight, ArrowLeft, Wand2, Loader2, Upload } from "lucide-react";
import { useRef } from "react";
import { PRESET_PERSONAS, Persona, saveOnboardingState } from "@/lib/personas";

type Step = "welcome" | "select" | "custom" | "confirm";

const Onboarding = () => {
  const navigate = useNavigate();
  const [step, setStep] = useState<Step>("welcome");
  const [selected, setSelected] = useState<Persona | null>(null);
  const [customName, setCustomName] = useState("");
  const [customDescription, setCustomDescription] = useState("");
  const [customAvatar, setCustomAvatar] = useState<string | null>(null);
  const [generating, setGenerating] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleSelectPreset = (persona: Persona) => {
    setSelected(persona);
    setStep("confirm");
  };

  const handleGenerateAvatar = async () => {
    if (!customDescription.trim()) return;
    setGenerating(true);
    // Placeholder: In production this calls the backend /api/character/generate endpoint
    // For now, simulate a delay and use a placeholder
    await new Promise((r) => setTimeout(r, 2000));
    // TODO: Replace with actual Gemini image generation via backend
    setCustomAvatar("/placeholder.svg");
    setGenerating(false);
  };

  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (!file.type.startsWith("image/")) return;
    const reader = new FileReader();
    reader.onload = () => setCustomAvatar(reader.result as string);
    reader.readAsDataURL(file);
  };

  const handleCustomConfirm = () => {
    const persona: Persona = {
      id: "custom",
      name: customName || "My Companion",
      title: "Health Companion",
      language: "English",
      languageCode: "en",
      avatar: customAvatar || "/placeholder.svg",
      greeting: `Hello! I'm ${customName || "your companion"}, ready to help with your health.`,
      description: customDescription,
    };
    setSelected(persona);
    setStep("confirm");
  };

  const handleFinish = () => {
    if (!selected) return;
    saveOnboardingState({
      persona: selected,
      customAvatar: selected.id === "custom" ? customAvatar || undefined : undefined,
      completed: true,
    });
    navigate("/");
  };

  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-background px-4 py-12">
      <AnimatePresence mode="wait">
        {/* Step: Welcome */}
        {step === "welcome" && (
          <motion.div
            key="welcome"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
            className="max-w-lg text-center"
          >
            <div className="mx-auto mb-6 flex h-20 w-20 items-center justify-center rounded-full bg-primary/10">
              <Sparkles size={36} className="text-primary" />
            </div>
            <h1 className="font-display text-4xl font-bold tracking-tight lg:text-5xl">
              Welcome to <em className="text-primary">MedLive</em>
            </h1>
            <p className="mt-4 text-lg text-muted-foreground">
              Your AI health guardian that speaks your language, sees your pills, and knows your name.
            </p>
            <p className="mt-2 text-muted-foreground">
              Let's set up your personal health companion.
            </p>
            <button
              onClick={() => setStep("select")}
              className="mt-8 inline-flex items-center gap-2 rounded-md bg-primary px-8 py-3 font-mono text-sm uppercase tracking-widest text-primary-foreground transition-colors hover:bg-primary/90"
            >
              Get Started <ArrowRight size={16} />
            </button>
          </motion.div>
        )}

        {/* Step: Select Persona */}
        {step === "select" && (
          <motion.div
            key="select"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
            className="w-full max-w-3xl"
          >
            <button
              onClick={() => setStep("welcome")}
              className="mb-6 inline-flex items-center gap-1 font-mono text-xs uppercase tracking-widest text-muted-foreground transition-colors hover:text-foreground"
            >
              <ArrowLeft size={14} /> Back
            </button>
            <h2 className="font-display text-3xl font-bold tracking-tight">
              Choose your <em className="text-primary">companion</em>
            </h2>
            <p className="mt-2 mb-8 text-muted-foreground">
              Pick a preset persona or create your own custom companion.
            </p>

            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              {PRESET_PERSONAS.map((persona) => (
                <button
                  key={persona.id}
                  onClick={() => handleSelectPreset(persona)}
                  className="group flex items-start gap-4 rounded-lg border border-border bg-card p-5 text-left transition-all duration-150 hover:border-primary hover:shadow-md"
                >
                  <img
                    src={persona.avatar}
                    alt={persona.name}
                    className="h-16 w-16 shrink-0 rounded-full border-2 border-border object-cover transition-all group-hover:border-primary"
                  />
                  <div className="min-w-0">
                    <h3 className="font-display text-lg font-bold">{persona.name}</h3>
                    <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
                      {persona.title} · {persona.language}
                    </p>
                    <p className="mt-1.5 text-sm text-muted-foreground">{persona.description}</p>
                    <p className="mt-2 text-sm italic text-foreground/70">"{persona.greeting}"</p>
                  </div>
                </button>
              ))}

              {/* Custom option */}
              <button
                onClick={() => setStep("custom")}
                className="group flex items-start gap-4 rounded-lg border-2 border-dashed border-border bg-card p-5 text-left transition-all duration-150 hover:border-primary hover:shadow-md"
              >
                <div className="flex h-16 w-16 shrink-0 items-center justify-center rounded-full border-2 border-dashed border-muted-foreground/30 transition-all group-hover:border-primary">
                  <Wand2 size={24} className="text-muted-foreground transition-colors group-hover:text-primary" />
                </div>
                <div className="min-w-0">
                  <h3 className="font-display text-lg font-bold">Create Your Own</h3>
                  <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
                    Custom · Any Language
                  </p>
                  <p className="mt-1.5 text-sm text-muted-foreground">
                    Describe your ideal health companion and we'll bring them to life with AI.
                  </p>
                </div>
              </button>
            </div>
          </motion.div>
        )}

        {/* Step: Custom persona */}
        {step === "custom" && (
          <motion.div
            key="custom"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
            className="w-full max-w-lg"
          >
            <button
              onClick={() => setStep("select")}
              className="mb-6 inline-flex items-center gap-1 font-mono text-xs uppercase tracking-widest text-muted-foreground transition-colors hover:text-foreground"
            >
              <ArrowLeft size={14} /> Back
            </button>
            <h2 className="font-display text-3xl font-bold tracking-tight">
              Create your <em className="text-primary">companion</em>
            </h2>
            <p className="mt-2 mb-8 text-muted-foreground">
              Describe your ideal health companion — personality, appearance, anything.
            </p>

            <div className="space-y-4">
              <div>
                <label className="mb-1.5 block font-mono text-xs uppercase tracking-widest text-muted-foreground">
                  Companion Name
                </label>
                <input
                  type="text"
                  value={customName}
                  onChange={(e) => setCustomName(e.target.value)}
                  placeholder="e.g., Dr. Ananya, Abuela Rosa…"
                  className="w-full rounded-md border border-border bg-background px-4 py-2.5 text-sm focus:border-primary focus:outline-none"
                />
              </div>
              <div>
                <label className="mb-1.5 block font-mono text-xs uppercase tracking-widest text-muted-foreground">
                  Description
                </label>
                <textarea
                  value={customDescription}
                  onChange={(e) => setCustomDescription(e.target.value)}
                  placeholder="e.g., A warm grandmotherly figure with grey hair and glasses who speaks Kannada with gentle humor…"
                  rows={4}
                  className="w-full resize-none rounded-md border border-border bg-background px-4 py-2.5 text-sm focus:border-primary focus:outline-none"
                />
              </div>

              {/* Avatar preview / upload */}
              <div className="flex flex-col items-center gap-3">
                <input
                  ref={fileInputRef}
                  type="file"
                  accept="image/*"
                  onChange={handleFileUpload}
                  className="hidden"
                />
                {customAvatar ? (
                  <button
                    type="button"
                    onClick={() => fileInputRef.current?.click()}
                    className="group relative"
                    title="Click to change photo"
                  >
                    <img
                      src={customAvatar}
                      alt="Avatar"
                      className="h-32 w-32 rounded-full border-4 border-primary/20 object-cover transition-all group-hover:opacity-70"
                    />
                    <div className="absolute inset-0 flex items-center justify-center rounded-full opacity-0 transition-opacity group-hover:opacity-100">
                      <Upload size={24} className="text-foreground" />
                    </div>
                  </button>
                ) : (
                  <button
                    type="button"
                    onClick={() => fileInputRef.current?.click()}
                    className="flex h-32 w-32 flex-col items-center justify-center gap-2 rounded-full border-2 border-dashed border-border text-muted-foreground transition-colors hover:border-primary hover:text-primary"
                  >
                    <Upload size={24} />
                    <span className="font-mono text-[9px] uppercase tracking-widest">Upload Photo</span>
                  </button>
                )}
              </div>

              <div className="flex gap-3">
                <button
                  onClick={handleGenerateAvatar}
                  disabled={!customDescription.trim() || generating}
                  className="inline-flex flex-1 items-center justify-center gap-2 rounded-md border border-border bg-card px-4 py-2.5 font-mono text-xs uppercase tracking-widest text-foreground transition-colors hover:bg-secondary disabled:opacity-40"
                >
                  {generating ? (
                    <Loader2 size={14} className="animate-spin" />
                  ) : (
                    <Wand2 size={14} />
                  )}
                  {generating ? "Generating…" : "AI Generate"}
                </button>
                <button
                  onClick={handleCustomConfirm}
                  disabled={!customName.trim()}
                  className="inline-flex flex-1 items-center justify-center gap-2 rounded-md bg-primary px-4 py-2.5 font-mono text-xs uppercase tracking-widest text-primary-foreground transition-colors hover:bg-primary/90 disabled:opacity-40"
                >
                  Continue <ArrowRight size={14} />
                </button>
              </div>
            </div>
          </motion.div>
        )}

        {/* Step: Confirm */}
        {step === "confirm" && selected && (
          <motion.div
            key="confirm"
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.95 }}
            className="max-w-md text-center"
          >
            <motion.img
              initial={{ scale: 0.8, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              transition={{ delay: 0.1, type: "spring", stiffness: 200 }}
              src={selected.avatar}
              alt={selected.name}
              className="mx-auto mb-6 h-32 w-32 rounded-full border-4 border-primary/20 object-cover shadow-lg shadow-primary/10"
            />
            <h2 className="font-display text-3xl font-bold tracking-tight">
              Meet <em className="text-primary">{selected.name}</em>
            </h2>
            <p className="mt-1 font-mono text-xs uppercase tracking-widest text-muted-foreground">
              {selected.title} · {selected.language}
            </p>
            <p className="mt-4 text-lg italic text-muted-foreground">
              "{selected.greeting}"
            </p>

            <div className="mt-8 flex items-center justify-center gap-3">
              <button
                onClick={() => setStep("select")}
                className="inline-flex items-center gap-1 rounded-md border border-border px-6 py-2.5 font-mono text-xs uppercase tracking-widest text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
              >
                <ArrowLeft size={14} /> Change
              </button>
              <button
                onClick={handleFinish}
                className="inline-flex items-center gap-2 rounded-md bg-primary px-8 py-2.5 font-mono text-xs uppercase tracking-widest text-primary-foreground transition-colors hover:bg-primary/90"
              >
                Start Talking <ArrowRight size={14} />
              </button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};

export default Onboarding;
