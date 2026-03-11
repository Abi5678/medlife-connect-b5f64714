import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import { Sparkles, ArrowRight, ArrowLeft, Wand2, Loader2, Upload, User } from "lucide-react";
import { useRef } from "react";
import { PRESET_PERSONAS, Persona, saveOnboardingState } from "@/lib/personas";
import { saveProfile, generateAvatar } from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";

type Step = "welcome" | "select" | "custom" | "details" | "confirm";

/** Convert image URL (e.g. bundled asset) to data URL for Firestore. */
async function imageUrlToBase64(url: string): Promise<string> {
  const res = await fetch(url);
  const blob = await res.blob();
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onloadend = () => resolve(reader.result as string);
    reader.onerror = reject;
    reader.readAsDataURL(blob);
  });
}

const Onboarding = () => {
  const navigate = useNavigate();
  const [step, setStep] = useState<Step>("welcome");
  const [selected, setSelected] = useState<Persona | null>(null);
  const [customName, setCustomName] = useState("");
  const [customDescription, setCustomDescription] = useState("");
  const [customAvatar, setCustomAvatar] = useState<string | null>(null);
  const [generating, setGenerating] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Patient Details State
  const { getIdToken } = useAuth();
  const [userAvatar, setUserAvatar] = useState<string | null>(null);
  const [userGenerating, setUserGenerating] = useState(false);
  const [displayName, setDisplayName] = useState("");
  const [dietaryPreference, setDietaryPreference] = useState("None");
  const [allergies, setAllergies] = useState("");
  const [conditions, setConditions] = useState("");
  const [currentMedications, setCurrentMedications] = useState("");
  const [emergencyName, setEmergencyName] = useState("");
  const [emergencyPhone, setEmergencyPhone] = useState("");
  const [bloodType, setBloodType] = useState("");
  const [primaryDoctor, setPrimaryDoctor] = useState("");

  const handleSelectPreset = (persona: Persona) => {
    setSelected(persona);
    setStep("details");
  };

  const handleGenerateAvatar = async () => {
    if (!customDescription.trim()) return;
    setGenerating(true);
    try {
      const formData = new FormData();
      formData.append("companion_name", customName || "My Companion");
      formData.append("avatar_description", customDescription);

      const res = await generateAvatar(formData);
      setCustomAvatar(res.avatar_b64);
    } catch (e) {
      console.error("Failed to generate avatar", e);
      // fallback
      if (!customAvatar) {
        setCustomAvatar("/placeholder.svg");
      }
    } finally {
      setGenerating(false);
    }
  };

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (!file.type.startsWith("image/")) return;

    setGenerating(true);
    try {
      const formData = new FormData();
      formData.append("companion_name", customName || "My Companion");
      // Use description if provided, otherwise default to the tech wear prompt
      formData.append("avatar_description", customDescription || "Wearing casual tech wear in navy blue");
      formData.append("photo", file);

      const res = await generateAvatar(formData);
      setCustomAvatar(res.avatar_b64);
    } catch (error) {
      console.error("Failed to generate avatar from photo", error);
      // Fallback: just show the uploaded photo locally if generation fails
      const reader = new FileReader();
      reader.onload = () => setCustomAvatar(reader.result as string);
      reader.readAsDataURL(file);
    } finally {
      setGenerating(false);
    }
  };

  const handleUserFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (!file.type.startsWith("image/")) return;

    setUserGenerating(true);
    try {
      const img = new Image();
      img.onload = () => {
        const canvas = document.createElement("canvas");
        const MAX_DIM = 400;
        let width = img.width;
        let height = img.height;

        if (width > height) {
          if (width > MAX_DIM) {
            height = Math.round((height * MAX_DIM) / width);
            width = MAX_DIM;
          }
        } else {
          if (height > MAX_DIM) {
            width = Math.round((width * MAX_DIM) / height);
            height = MAX_DIM;
          }
        }

        canvas.width = width;
        canvas.height = height;
        const ctx = canvas.getContext("2d");
        ctx?.drawImage(img, 0, 0, width, height);

        const dataUrl = canvas.toDataURL("image/jpeg", 0.7);
        setUserAvatar(dataUrl);
        setUserGenerating(false);
      };
      img.onerror = () => {
        console.error("Failed to read user photo");
        setUserGenerating(false);
      };
      img.src = URL.createObjectURL(file);
    } catch (error) {
      console.error("Failed to process user photo", error);
      setUserGenerating(false);
    }
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
    setStep("details");
  };

  const handleDetailsConfirm = () => {
    setStep("confirm");
  };

  const handleFinish = async () => {
    if (!selected) return;

    // For preset personas, convert avatar URL to base64 so Firestore has it (fixes stale avatar in Voice Guardian)
    let presetAvatarB64: string | undefined;
    if (selected.id !== "custom" && selected.avatar) {
      try {
        presetAvatarB64 = await imageUrlToBase64(selected.avatar);
      } catch (e) {
        console.warn("Failed to convert preset avatar to base64:", e);
      }
    }

    // Save to Firestore via API
    try {
      const token = await getIdToken();
      if (token) {
        await saveProfile({
          display_name: displayName,
          allergies: allergies,
          conditions: conditions,
          dietary_preference: dietaryPreference,
          current_medications: currentMedications,
          emergency_contact_name: emergencyName,
          emergency_contact_phone: emergencyPhone,
          blood_type: bloodType,
          primary_doctor: primaryDoctor,
          companion_name: selected.name,
          language: selected.language,
          avatar_b64: selected.id === "custom" ? customAvatar : presetAvatarB64,
          user_avatar_b64: userAvatar || undefined
        }, token);
      }
    } catch (e) {
      console.error("Failed to save profile during onboarding", e);
    }

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
              Pick a persona or create your own custom companion.
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

              <div className="flex gap-3 mt-6">
                <button
                  onClick={handleGenerateAvatar}
                  disabled={generating}
                  className="inline-flex flex-1 items-center justify-center gap-2 rounded-md border border-border bg-card px-4 py-2.5 font-mono text-xs uppercase tracking-widest text-foreground transition-colors hover:bg-secondary disabled:opacity-40 shadow-sm"
                >
                  {generating ? (
                    <Loader2 size={14} className="animate-spin" />
                  ) : (
                    <Sparkles size={14} className="text-primary" />
                  )}
                  {generating ? "Generating…" : "AI Generate"}
                </button>
                <button
                  onClick={handleCustomConfirm}
                  disabled={!customName.trim()}
                  className="inline-flex flex-1 items-center justify-center gap-2 rounded-md bg-primary px-4 py-2.5 font-mono text-xs uppercase tracking-widest text-primary-foreground transition-colors hover:bg-primary/90 disabled:opacity-40 shadow-sm"
                >
                  Continue <ArrowRight size={14} />
                </button>
              </div>
            </div>
          </motion.div>
        )}

        {/* Step: Patient Details */}
        {step === "details" && (
          <motion.div
            key="details"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
            className="w-full max-w-lg"
          >
            <button
              onClick={() => setStep(selected?.id === "custom" ? "custom" : "select")}
              className="mb-6 inline-flex items-center gap-1 font-mono text-xs uppercase tracking-widest text-muted-foreground transition-colors hover:text-foreground"
            >
              <ArrowLeft size={14} /> Back
            </button>
            <h2 className="font-display text-3xl font-bold tracking-tight">
              A bit about <em className="text-primary">you</em>
            </h2>
            <p className="mt-2 mb-8 text-muted-foreground">
              So {selected?.name} knows how to assist you and safely suggest recipes.
            </p>

            <div className="space-y-4">
              <div className="flex flex-col items-center justify-center mb-6">
                <div className="relative flex h-24 w-24 items-center justify-center rounded-full bg-primary/10 overflow-hidden mb-3">
                  {userAvatar ? (
                    <img src={userAvatar.startsWith('data:') ? userAvatar : `data:image/jpeg;base64,${userAvatar}`} alt="Your Profile" className="h-full w-full object-cover" />
                  ) : (
                    <User size={32} className="text-primary/50" />
                  )}
                  {userGenerating && (
                    <div className="absolute inset-0 flex items-center justify-center bg-background/50 backdrop-blur-sm">
                      <Loader2 className="animate-spin text-primary" size={24} />
                    </div>
                  )}
                </div>
                <label className="cursor-pointer rounded-md border border-border bg-card px-4 py-2 text-xs font-mono uppercase tracking-widest transition-colors hover:bg-secondary">
                  <span>{userGenerating ? "Uploading..." : "Upload Your Photo"}</span>
                  <input
                    type="file"
                    className="sr-only"
                    accept="image/*"
                    onChange={handleUserFileUpload}
                    disabled={userGenerating}
                  />
                </label>
              </div>

              <div>
                <label className="mb-1.5 block font-mono text-xs uppercase tracking-widest text-muted-foreground">
                  Your Full Name
                </label>
                <input
                  type="text"
                  value={displayName}
                  onChange={(e) => setDisplayName(e.target.value)}
                  placeholder="e.g., Amma Patel"
                  className="w-full rounded-md border border-border bg-background px-4 py-2.5 text-sm focus:border-primary focus:outline-none"
                />
              </div>

              <div>
                <label className="mb-1.5 block font-mono text-xs uppercase tracking-widest text-muted-foreground">
                  Dietary Preference
                </label>
                <select
                  value={dietaryPreference}
                  onChange={(e) => setDietaryPreference(e.target.value)}
                  className="w-full rounded-md border border-border bg-background px-4 py-2.5 text-sm focus:border-primary focus:outline-none"
                >
                  <option value="None">None</option>
                  <option value="Vegetarian">Vegetarian</option>
                  <option value="Vegan">Vegan</option>
                  <option value="Pescatarian">Pescatarian</option>
                  <option value="Keto">Keto</option>
                  <option value="Low Sodium">Low Sodium</option>
                  <option value="Diabetic / Low Glycemic">Diabetic / Low Glycemic</option>
                </select>
              </div>

              <div>
                <label className="mb-1.5 block font-mono text-xs uppercase tracking-widest text-muted-foreground">
                  Food Allergies
                </label>
                <input
                  type="text"
                  value={allergies}
                  onChange={(e) => setAllergies(e.target.value)}
                  placeholder="e.g., Peanuts, Shellfish, Gluten (comma separated)"
                  className="w-full rounded-md border border-border bg-background px-4 py-2.5 text-sm focus:border-primary focus:outline-none"
                />
                <p className="mt-1 text-xs text-muted-foreground">Leave blank if none.</p>
              </div>

              <div>
                <label className="mb-1.5 block font-mono text-xs uppercase tracking-widest text-muted-foreground">
                  Current Medications (Optional)
                </label>
                <textarea
                  value={currentMedications}
                  onChange={(e) => setCurrentMedications(e.target.value)}
                  placeholder="e.g., Lisinopril 10mg, Metformin"
                  rows={2}
                  className="w-full resize-none rounded-md border border-border bg-background px-4 py-2.5 text-sm focus:border-primary focus:outline-none"
                />
              </div>

              <div>
                <label className="mb-1.5 block font-mono text-xs uppercase tracking-widest text-muted-foreground">
                  Conditions
                </label>
                <input
                  type="text"
                  value={conditions}
                  onChange={(e) => setConditions(e.target.value)}
                  placeholder="e.g., Hypertension, Asthma"
                  className="w-full rounded-md border border-border bg-background px-4 py-2.5 text-sm focus:border-primary focus:outline-none"
                />
              </div>

              <div>
                <label className="mb-1.5 block font-mono text-xs uppercase tracking-widest text-muted-foreground">
                  Blood Type
                </label>
                <input
                  type="text"
                  value={bloodType}
                  onChange={(e) => setBloodType(e.target.value)}
                  placeholder="e.g., O+, A-"
                  className="w-full rounded-md border border-border bg-background px-4 py-2.5 text-sm focus:border-primary focus:outline-none"
                />
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label className="mb-1.5 block font-mono text-xs uppercase tracking-widest text-muted-foreground">
                    Emergency Contact Name
                  </label>
                  <input
                    type="text"
                    value={emergencyName}
                    onChange={(e) => setEmergencyName(e.target.value)}
                    placeholder="e.g., Jane Doe"
                    className="w-full rounded-md border border-border bg-background px-4 py-2.5 text-sm focus:border-primary focus:outline-none"
                  />
                </div>
                <div>
                  <label className="mb-1.5 block font-mono text-xs uppercase tracking-widest text-muted-foreground">
                    Emergency Contact Phone
                  </label>
                  <input
                    type="text"
                    value={emergencyPhone}
                    onChange={(e) => setEmergencyPhone(e.target.value)}
                    placeholder="e.g., 555-123-4567"
                    className="w-full rounded-md border border-border bg-background px-4 py-2.5 text-sm focus:border-primary focus:outline-none"
                  />
                </div>
              </div>

              <div>
                <label className="mb-1.5 block font-mono text-xs uppercase tracking-widest text-muted-foreground">
                  Primary Doctor
                </label>
                <input
                  type="text"
                  value={primaryDoctor}
                  onChange={(e) => setPrimaryDoctor(e.target.value)}
                  placeholder="e.g., Dr. Smith"
                  className="w-full rounded-md border border-border bg-background px-4 py-2.5 text-sm focus:border-primary focus:outline-none"
                />
              </div>

              <div className="pt-4">
                <button
                  onClick={handleDetailsConfirm}
                  disabled={!displayName.trim()}
                  className="flex w-full items-center justify-center gap-2 rounded-md bg-primary px-4 py-3 font-mono text-sm uppercase tracking-widest text-primary-foreground transition-colors hover:bg-primary/90 disabled:opacity-40"
                >
                  Confirm Profile <ArrowRight size={16} />
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
                onClick={() => setStep("details")}
                className="inline-flex items-center gap-1 rounded-md border border-border px-6 py-2.5 font-mono text-xs uppercase tracking-widest text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
              >
                <ArrowLeft size={14} /> Back
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
