import { REST_API_BASE_URL } from "./voiceConfig";

/** Helper: build headers with Firebase auth token */
function authHeaders(token: string): HeadersInit {
  return {
    "Content-Type": "application/json",
    Authorization: `Bearer ${token}`,
  };
}

async function handleResponse<T = unknown>(res: Response): Promise<T> {
  if (!res.ok) {
    const text = await res.text().catch(() => "Unknown error");
    throw new Error(`API ${res.status}: ${text}`);
  }
  return res.json();
}

// ---------------------------------------------------------------------------
// Dashboard & Profile
// ---------------------------------------------------------------------------

export async function getDashboard(patientUid: string, token: string) {
  const res = await fetch(
    `${REST_API_BASE_URL}/api/dashboard?patient_uid=${encodeURIComponent(patientUid)}`,
    { headers: authHeaders(token) },
  );
  return handleResponse<{
    adherence: { score: number; rating: string; details: Record<string, unknown>[] };
    blood_sugar_trend: unknown;
    blood_pressure_trend: unknown;
    digest: { medications: unknown[]; vitals: unknown[]; meals: unknown[] };
  }>(res);
}

export async function getProfile(token: string) {
  const res = await fetch(`${REST_API_BASE_URL}/api/auth/profile`, {
    headers: authHeaders(token),
  });
  return handleResponse(res);
}

export async function saveProfile(data: Record<string, unknown>, token: string) {
  const res = await fetch(`${REST_API_BASE_URL}/api/auth/profile`, {
    method: "POST",
    headers: authHeaders(token),
    body: JSON.stringify(data),
  });
  return handleResponse(res);
}

// ---------------------------------------------------------------------------
// Medications
// ---------------------------------------------------------------------------

export async function getMedications(token: string) {
  const res = await fetch(`${REST_API_BASE_URL}/api/medications`, {
    headers: authHeaders(token),
  });
  return handleResponse<{ medications: unknown[] }>(res);
}

export async function addMedication(
  data: { name: string; dosage?: string; purpose?: string; times?: string[]; schedule_type?: string },
  token: string,
) {
  const res = await fetch(`${REST_API_BASE_URL}/api/medications`, {
    method: "POST",
    headers: authHeaders(token),
    body: JSON.stringify(data),
  });
  return handleResponse(res);
}

export async function logMedicationTaken(medicationName: string, token: string) {
  const res = await fetch(`${REST_API_BASE_URL}/api/medications/taken`, {
    method: "POST",
    headers: authHeaders(token),
    body: JSON.stringify({ medication_name: medicationName }),
  });
  return handleResponse(res);
}

// ---------------------------------------------------------------------------
// Appointments
// ---------------------------------------------------------------------------

export async function getAppointments(patientUid: string, token: string) {
  const res = await fetch(
    `${REST_API_BASE_URL}/api/appointments?patient_uid=${encodeURIComponent(patientUid)}`,
    { headers: authHeaders(token) },
  );
  return handleResponse<{ appointments: unknown[] }>(res);
}

// ---------------------------------------------------------------------------
// Scanning (Prescriptions & Lab Reports)
// ---------------------------------------------------------------------------

export async function scanDocument(imageB64: string, scanType: "prescription" | "report", token: string) {
  const res = await fetch(`${REST_API_BASE_URL}/api/scan`, {
    method: "POST",
    headers: authHeaders(token),
    body: JSON.stringify({ image_b64: imageB64, scan_type: scanType }),
  });
  return handleResponse(res);
}

// ---------------------------------------------------------------------------
// Food
// ---------------------------------------------------------------------------

export async function analyzeFood(imageBase64: string) {
  const res = await fetch(`${REST_API_BASE_URL}/api/food/analyze`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ image_base64: imageBase64 }),
  });
  return handleResponse<{
    food_items: string[];
    calories: number;
    protein_g: number;
    carbs_g: number;
    fat_g: number;
  }>(res);
}

export async function logFood(
  data: { uid: string; food_items: string[]; calories: number; protein_g: number; carbs_g: number; fat_g: number },
) {
  const res = await fetch(`${REST_API_BASE_URL}/api/food/log`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  return handleResponse(res);
}

// ---------------------------------------------------------------------------
// Family
// ---------------------------------------------------------------------------

export async function generateFamilyCode(token: string) {
  const res = await fetch(`${REST_API_BASE_URL}/api/family/code/generate`, {
    method: "POST",
    headers: authHeaders(token),
  });
  return handleResponse<{ code: string; expires_at: string }>(res);
}

export async function verifyFamilyCode(code: string, token: string) {
  const res = await fetch(`${REST_API_BASE_URL}/api/family/code/verify`, {
    method: "POST",
    headers: authHeaders(token),
    body: JSON.stringify({ code }),
  });
  return handleResponse<{ parent_name: string; linked: boolean }>(res);
}

export async function generateAvatar(formData: FormData) {
  const res = await fetch(`${REST_API_BASE_URL}/api/avatar/generate`, {
    method: "POST",
    body: formData, // the browser sets the correct Content-Type for FormData automatically
  });
  return handleResponse<{ avatar_b64: string }>(res);
}

// ---------------------------------------------------------------------------
// Config
// ---------------------------------------------------------------------------

export async function getPublicConfig() {
  const res = await fetch(`${REST_API_BASE_URL}/api/config`);
  return handleResponse<{ vapidKey: string; skipAuth: boolean }>(res);
}
