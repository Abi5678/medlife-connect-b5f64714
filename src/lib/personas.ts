import avatarDrPriya from "@/assets/avatar-dr-priya.png";
import avatarElena from "@/assets/avatar-elena.png";
import avatarDrChen from "@/assets/avatar-dr-chen.png";
import avatarNurseMaya from "@/assets/avatar-nurse-maya.png";

export interface Persona {
  id: string;
  name: string;
  title: string;
  language: string;
  languageCode: string;
  avatar: string;
  greeting: string;
  description: string;
}

export const PRESET_PERSONAS: Persona[] = [
  {
    id: "dr-priya",
    name: "Dr. Priya",
    title: "Health Companion",
    language: "Hindi",
    languageCode: "hi",
    avatar: avatarDrPriya,
    greeting: "Namaste ji! Main Dr. Priya hoon, aapki health companion.",
    description: "Warm Indian doctor who speaks Hindi with a caring, family-like tone.",
  },
  {
    id: "elena",
    name: "Enfermera Elena",
    title: "Health Guardian",
    language: "Spanish",
    languageCode: "es",
    avatar: avatarElena,
    greeting: "¡Hola, mi amor! Soy Elena, tu enfermera de confianza.",
    description: "Caring Latina nurse who speaks Spanish with warmth and affection.",
  },
  {
    id: "dr-chen",
    name: "Dr. Chen",
    title: "Health Advisor",
    language: "English",
    languageCode: "en",
    avatar: avatarDrChen,
    greeting: "Good morning! I'm Dr. Chen, your personal health advisor.",
    description: "Professional physician who speaks English with calm, clear guidance.",
  },
  {
    id: "nurse-maya",
    name: "Nurse Maya",
    title: "Wellness Coach",
    language: "English",
    languageCode: "en",
    avatar: avatarNurseMaya,
    greeting: "Hey there! I'm Maya, your wellness coach. How are you feeling today?",
    description: "Friendly, energetic young nurse focused on holistic wellness.",
  },
];

export interface OnboardingState {
  persona: Persona | null;
  customName?: string;
  customAvatar?: string;
  completed: boolean;
}

const STORAGE_KEY = "medlive_onboarding";

export function getOnboardingState(): OnboardingState {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) return JSON.parse(raw);
  } catch (e) {
    console.error("Failed to parse onboarding state:", e);
  }
  return { persona: null, completed: false };
}

export function saveOnboardingState(state: OnboardingState) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
}

export function clearOnboarding() {
  localStorage.removeItem(STORAGE_KEY);
}
