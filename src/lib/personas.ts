import avatarDrPriya from "@/assets/avatar-dr-priya.png";
import avatarElena from "@/assets/avatar-elena.png";
import avatarDrChen from "@/assets/avatar-dr-chen.png";
import avatarNurseMaya from "@/assets/avatar-nurse-maya.png";
import healiBalanced from "@/assets/heali_balanced.png";
import healiCalm from "@/assets/heali_calm.png";
import healiEnergetic from "@/assets/heali_energetic.png";
import healiInformative from "@/assets/heali_informative.png";

export interface Persona {
  id: string;
  name: string;
  title: string;
  language: string;
  languageCode: string;
  avatar: string;
  greeting: string;
  description: string;
  /** Gemini voice name for backend (e.g. Aoede, Kore). Used when saving profile from onboarding. */
  voiceName?: string;
}

/** Voice-centric Heali options for the onboarding select step. */
export const HEALI_VOICES: Persona[] = [
  {
    id: "heali-balanced",
    name: "Heali (Balanced)",
    title: "Voice · Balanced",
    language: "English",
    languageCode: "en",
    avatar: healiBalanced,
    greeting: "Hello, I'm Heali. I'm here to support you.",
    description: "A versatile, caring voice that feels familiar and supportive",
    voiceName: "Aoede",
  },
  {
    id: "heali-calm",
    name: "Heali (Calm)",
    title: "Voice · Calm",
    language: "English",
    languageCode: "en",
    avatar: healiCalm,
    greeting: "It's okay. Take a deep breath. I'm with you.",
    description: "A deeply calming and reassuring voice, perfect for anxiety-free guidance",
    voiceName: "Kore",
  },
  {
    id: "heali-energetic",
    name: "Heali (Energetic)",
    title: "Voice · Energetic",
    language: "English",
    languageCode: "en",
    avatar: healiEnergetic,
    greeting: "You've got this! Let's hit that goal today!",
    description: "An energetic and motivational voice to keep you moving and inspired",
    voiceName: "Puck",
  },
  {
    id: "heali-informative",
    name: "Heali (Informative)",
    title: "Voice · Informative",
    language: "English",
    languageCode: "en",
    avatar: healiInformative,
    greeting: "Today's data shows good progress. Let's review the plan.",
    description: "A clear, informative voice that provides direct and trustworthy health data",
    voiceName: "Charon",
  },
];

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

const STORAGE_KEY = "heali_onboarding";
const LEGACY_STORAGE_KEY = "medlive_onboarding";

export function getOnboardingState(): OnboardingState {
  try {
    let raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) {
      const legacy = localStorage.getItem(LEGACY_STORAGE_KEY);
      if (legacy) {
        localStorage.setItem(STORAGE_KEY, legacy);
        localStorage.removeItem(LEGACY_STORAGE_KEY);
        raw = legacy;
      }
    }
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
