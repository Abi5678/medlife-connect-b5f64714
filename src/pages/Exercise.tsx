import { useState, useRef, useEffect, useCallback } from "react";
import { AnimatePresence, motion } from "framer-motion";
import {
  Play, Square, Camera, CameraOff, Timer, Trophy,
  Activity, Wind, MoveHorizontal, Dumbbell, Wifi, WifiOff,
} from "lucide-react";
import AppLayout from "@/components/AppLayout";
import { useVoiceGuardian } from "@/hooks/useVoiceGuardian";
import { useAuth } from "@/contexts/AuthContext";
import { toast } from "@/hooks/use-toast";
import { useUIEvent } from "@/hooks/useUIEventStore";
import { pushUIEvent } from "@/hooks/useUIEventStore";
import type { UIEvent } from "@/hooks/useVoiceGuardian";

const PHASE_INFO = [
  { name: "Breathing", icon: Wind, color: "text-blue-400", bg: "bg-blue-500/10", border: "border-blue-500/30" },
  { name: "Stretches", icon: MoveHorizontal, color: "text-amber-400", bg: "bg-amber-500/10", border: "border-amber-500/30" },
  { name: "Yoga", icon: Activity, color: "text-purple-400", bg: "bg-purple-500/10", border: "border-purple-500/30" },
  { name: "Cool-Down", icon: Wind, color: "text-emerald-400", bg: "bg-emerald-500/10", border: "border-emerald-500/30" },
];

const TOTAL_EXERCISES = 14;

/**
 * Injected as ?proactive_prompt= on the WebSocket URL.
 * Tells the root guardian agent to skip its standard greeting and route
 * SILENTLY to the exercise sub-agent, which will do the welcome itself.
 */
const EXERCISE_PROACTIVE_PROMPT =
  "[WELLNESS_SESSION_START]: The user has opened the dedicated Exercise & Wellness page. " +
  "Do NOT greet them as the guardian agent. Do NOT say a single word. " +
  "IMMEDIATELY route to the exercise sub-agent — it will welcome the user and start the session.";

type SessionState = "connecting" | "welcome" | "active" | "completed";

const Exercise = () => {
  const { user, getIdToken } = useAuth();
  const [sessionState, setSessionState] = useState<SessionState>("connecting");
  const [firebaseToken, setFirebaseToken] = useState<string>("demo");
  const [currentExercise, setCurrentExercise] = useState<string>("");
  const [exerciseNumber, setExerciseNumber] = useState(0);
  const [currentPhase, setCurrentPhase] = useState<string>("Breathing");
  const [postureNotes, setPostureNotes] = useState<string>("");
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [completionData, setCompletionData] = useState<Record<string, unknown> | null>(null);

  const [cameraActive, setCameraActive] = useState(false);
  const [exerciseCountdown, setExerciseCountdown] = useState<number | null>(null);
  const videoRef = useRef<HTMLVideoElement>(null);
  const cameraStreamRef = useRef<MediaStream | null>(null);
  const cameraIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const exerciseTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const exerciseNameRef = useRef<string>("");
  // Becomes true when the exercise countdown reaches zero; cleared on next exercise.
  const timerElapsedRef = useRef<boolean>(false);
  // Polls every 200 ms waiting for timer elapsed + agent silence before firing the signal.
  const waitForSpeechEndRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Set srcObject once the video element mounts (after cameraActive → true)
  useEffect(() => {
    if (cameraActive && videoRef.current && cameraStreamRef.current) {
      videoRef.current.srcObject = cameraStreamRef.current;
    }
  }, [cameraActive]);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const transcriptEndRef = useRef<HTMLDivElement>(null);
  const hasAutoConnected = useRef(false);

  // Listen for exercise UI events
  const sessionStarted = useUIEvent("exercise_session_started");
  const poseChange = useUIEvent("exercise_pose_change");
  const sessionCompleted = useUIEvent("exercise_session_completed");
  const timerStarted = useUIEvent("exercise_timer_started");

  // When agent calls start_exercise_session → start camera + timer
  useEffect(() => {
    if (sessionStarted) {
      setSessionState("active");
      startTimer();
      startCamera();
    }
  }, [sessionStarted]);

  useEffect(() => {
    if (poseChange) {
      const data = (poseChange.data ?? poseChange) as Record<string, unknown>;
      setCurrentExercise(String(data.exercise_name || ""));
      setExerciseNumber(Number(data.exercise_number || 0));
      setCurrentPhase(String(data.phase || "Breathing"));
      setPostureNotes(String(data.posture_notes || ""));
    }
  }, [poseChange]);

  useEffect(() => {
    if (sessionCompleted) {
      const data = (sessionCompleted.data ?? sessionCompleted) as Record<string, unknown>;
      setCompletionData(data);
      setSessionState("completed");
      stopTimer();
      stopCamera();
    }
  }, [sessionCompleted]);

  // Frontend exercise countdown — starts when agent calls await_exercise_completion.
  //
  // WHY we wait for the agent to stop speaking before firing the signal:
  // The backend converts sendText() to audio via macOS `say`, which Gemini receives as
  // user speech. If this audio fires while the agent is mid-coaching, Gemini's VAD detects
  // it as an interruption, which resets the agent's turn and can trigger a re-greeting.
  // By waiting until isSpeakingRef.current === false, we avoid the barge-in.
  useEffect(() => {
    if (!timerStarted) return;
    const data = (timerStarted.data ?? timerStarted) as Record<string, unknown>;
    const duration = Math.max(Number(data.duration_seconds || 30), 15);
    const name = String(data.exercise_name || "exercise");

    exerciseNameRef.current = name;
    timerElapsedRef.current = false;

    // Clear any previous timers
    if (exerciseTimerRef.current) clearInterval(exerciseTimerRef.current);
    if (waitForSpeechEndRef.current) clearInterval(waitForSpeechEndRef.current);
    setExerciseCountdown(duration);

    // Phase 1: countdown timer (purely visual + sets timerElapsedRef when done)
    let remaining = duration;
    exerciseTimerRef.current = setInterval(() => {
      remaining -= 1;
      setExerciseCountdown(remaining);
      if (remaining <= 0) {
        clearInterval(exerciseTimerRef.current!);
        exerciseTimerRef.current = null;
        setExerciseCountdown(null);
        timerElapsedRef.current = true;
      }
    }, 1000);

    // Phase 2: once timer elapsed, wait for agent to stop speaking (max 10 s),
    // then send a SHORT silent system signal so it doesn't appear in transcript
    // and doesn't interrupt the agent's "...5...4...3...2...1...and release!" speech.
    let waitedMs = 0;
    const MAX_WAIT_MS = 10_000;
    waitForSpeechEndRef.current = setInterval(() => {
      if (!timerElapsedRef.current) return; // still counting down
      waitedMs += 200;
      if (!isSpeakingRef.current || waitedMs >= MAX_WAIT_MS) {
        clearInterval(waitForSpeechEndRef.current!);
        waitForSpeechEndRef.current = null;
        // Brief bracketed signal — clearly a system token, not natural speech.
        // { silent: true } prevents it from showing as a "YOU" bubble.
        sendText(`[TIMER_COMPLETE]: ${exerciseNameRef.current}`, { silent: true });
      }
    }, 200);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [timerStarted]);

  const handleUIEvent = useCallback((event: UIEvent) => {
    pushUIEvent(event);
  }, []);

  const {
    status,
    isListening,
    isSpeaking,
    isSpeakingRef,
    transcript,
    connect,
    disconnect,
    sendText,
    sendImage,
    clearTranscript,
  } = useVoiceGuardian({
    userId: user?.uid,
    token: firebaseToken,
    persona: "en",
    patientName: user?.displayName || undefined,
    proactivePrompt: EXERCISE_PROACTIVE_PROMPT,
    onError: (msg) => {
      toast({ variant: "destructive", title: "Exercise Coach", description: msg });
    },
    onUIEvent: handleUIEvent,
  });

  // Auto-connect on page load and trigger exercise agent
  useEffect(() => {
    if (hasAutoConnected.current) return;
    hasAutoConnected.current = true;

    const autoConnect = async () => {
      // Ensure token is resolved before connecting
      const token = await getIdToken();
      if (token) setFirebaseToken(token);

      await connect();
      // The proactive prompt [WELLNESS_SESSION_START] already routes silently
      // to the exercise agent on connect — no sendText needed here.
      setSessionState("welcome");
    };

    autoConnect();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Auto-scroll transcript
  useEffect(() => {
    transcriptEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [transcript]);

  // Timer
  const startTimer = useCallback(() => {
    setElapsedSeconds(0);
    timerRef.current = setInterval(() => {
      setElapsedSeconds((prev) => prev + 1);
    }, 1000);
  }, []);

  const stopTimer = useCallback(() => {
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  // Camera with front-facing mode for posture
  const startCamera = useCallback(async () => {
    if (cameraStreamRef.current) return; // already active
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: "user", width: 640, height: 480 },
      });
      cameraStreamRef.current = stream;
      setCameraActive(true); // video element mounts → useEffect sets srcObject

      const canvas = document.createElement("canvas");
      canvas.width = 640;
      canvas.height = 480;
      const ctx = canvas.getContext("2d")!;

      cameraIntervalRef.current = setInterval(() => {
        if (videoRef.current && videoRef.current.readyState >= 2) {
          ctx.drawImage(videoRef.current, 0, 0, 640, 480);
          const dataUrl = canvas.toDataURL("image/jpeg", 0.6);
          const base64 = dataUrl.split(",")[1];
          sendImage(base64, "image/jpeg");
        }
      }, 1000);
    } catch {
      toast({
        variant: "destructive",
        title: "Camera",
        description: "Camera access denied. Camera is needed for posture feedback.",
      });
    }
  }, [sendImage]);

  const stopCamera = useCallback(() => {
    if (cameraIntervalRef.current) {
      clearInterval(cameraIntervalRef.current);
      cameraIntervalRef.current = null;
    }
    if (cameraStreamRef.current) {
      cameraStreamRef.current.getTracks().forEach((t) => t.stop());
      cameraStreamRef.current = null;
    }
    setCameraActive(false);
  }, []);

  const handleEndSession = useCallback(() => {
    disconnect();
    stopCamera();
    stopTimer();
    if (sessionState === "active" || sessionState === "welcome") {
      setSessionState("completed");
    }
  }, [disconnect, stopCamera, stopTimer, sessionState]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      stopCamera();
      stopTimer();
      if (exerciseTimerRef.current) clearInterval(exerciseTimerRef.current);
      if (waitForSpeechEndRef.current) clearInterval(waitForSpeechEndRef.current);
    };
  }, [stopCamera, stopTimer]);

  const formatTime = (seconds: number) => {
    const m = Math.floor(seconds / 60);
    const s = seconds % 60;
    return `${m.toString().padStart(2, "0")}:${s.toString().padStart(2, "0")}`;
  };

  const progressPercent = Math.round((exerciseNumber / TOTAL_EXERCISES) * 100);
  const isConnected = status === "connected" || status === "ready";
  const phaseInfo = PHASE_INFO.find((p) => p.name === currentPhase) || PHASE_INFO[0];

  return (
    <AppLayout>
      <div className="mb-12">
        <h1 className="font-display text-5xl font-bold tracking-tight lg:text-7xl">
          Exercise
          <br />
          <em className="text-emerald-400">& Wellness</em>
        </h1>
        <div className="mt-6 mb-8 h-1 max-w-32 bg-emerald-400" />
        <p className="max-w-lg text-lg text-muted-foreground">
          10-minute guided session with real-time posture coaching via camera
        </p>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* Left: Camera + Controls */}
        <div className="flex flex-col gap-6 lg:col-span-2">
          {/* Camera View */}
          <div className="relative overflow-hidden rounded-lg border border-border bg-card">
            <div className="relative flex aspect-video items-center justify-center bg-black/90">
              {cameraActive ? (
                <>
                  <video
                    ref={videoRef}
                    autoPlay
                    playsInline
                    muted
                    className="h-full w-full object-cover"
                    style={{ transform: "scaleX(-1)" }}
                  />
                  {/* Overlay badges */}
                  <div className="absolute top-3 left-3 flex items-center gap-2">
                    <div className="flex items-center gap-1.5 rounded bg-black/60 px-2 py-1">
                      <div className="h-2 w-2 animate-pulse rounded-full bg-red-500" />
                      <span className="font-mono text-[10px] text-white">LIVE</span>
                    </div>
                    {isSpeaking && (
                      <div className="flex items-center gap-1 rounded bg-emerald-600/80 px-2 py-1">
                        {[...Array(3)].map((_, i) => (
                          <motion.div
                            key={i}
                            animate={{ height: [3, 10, 3] }}
                            transition={{ repeat: Infinity, duration: 0.5, delay: i * 0.1 }}
                            className="w-0.5 rounded-full bg-white"
                          />
                        ))}
                        <span className="ml-1 font-mono text-[10px] text-white">Coach</span>
                      </div>
                    )}
                  </div>
                  <div className="absolute top-3 right-3 flex flex-col items-end gap-1.5">
                    <div className="rounded bg-black/60 px-3 py-1.5 font-mono text-lg font-bold text-white">
                      {formatTime(elapsedSeconds)}
                    </div>
                    {exerciseCountdown !== null && (
                      <motion.div
                        key={exerciseCountdown}
                        initial={{ scale: 1.15 }}
                        animate={{ scale: 1 }}
                        className={`rounded px-3 py-1 font-mono text-base font-bold ${exerciseCountdown <= 5 ? "bg-red-600/90 text-white" : "bg-emerald-600/80 text-white"}`}
                      >
                        {exerciseCountdown}s
                      </motion.div>
                    )}
                  </div>
                </>
              ) : (
                <div className="text-center">
                  {sessionState === "connecting" ? (
                    <>
                      <motion.div
                        animate={{ rotate: 360 }}
                        transition={{ repeat: Infinity, duration: 2, ease: "linear" }}
                        className="mx-auto mb-4"
                      >
                        <Activity size={48} strokeWidth={1} className="text-emerald-400/60" />
                      </motion.div>
                      <p className="font-mono text-sm uppercase tracking-widest text-muted-foreground">
                        Connecting to your wellness coach...
                      </p>
                    </>
                  ) : sessionState === "completed" ? (
                    <>
                      <Trophy size={48} strokeWidth={1} className="mx-auto mb-4 text-emerald-400/60" />
                      <p className="font-mono text-sm uppercase tracking-widest text-muted-foreground">
                        Session complete!
                      </p>
                    </>
                  ) : (
                    <>
                      <Dumbbell size={48} strokeWidth={1} className="mx-auto mb-4 text-emerald-400/40" />
                      <p className="font-mono text-sm uppercase tracking-widest text-muted-foreground">
                        {sessionState === "welcome"
                          ? "Your coach is ready — say \"let's go\" to begin!"
                          : "Ready to begin your wellness session"}
                      </p>
                    </>
                  )}
                </div>
              )}
            </div>

            {/* Controls bar */}
            <div className="flex items-center justify-between border-t border-border p-4">
              <div className="flex items-center gap-2">
                {status === "ready" ? (
                  <Wifi size={14} strokeWidth={1.5} className="text-success" />
                ) : isConnected ? (
                  <Wifi size={14} strokeWidth={1.5} className="animate-pulse text-primary" />
                ) : (
                  <WifiOff size={14} strokeWidth={1.5} className="text-muted-foreground" />
                )}
                <span className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
                  {status === "ready"
                    ? "Coach connected"
                    : status === "connecting"
                      ? "Connecting..."
                      : isConnected
                        ? "Connecting to coach..."
                        : "Disconnected"}
                </span>
              </div>
              <div className="flex gap-3">
                {(sessionState === "active" || sessionState === "welcome") && (
                  <button
                    onClick={handleEndSession}
                    className="flex items-center gap-2 rounded-md bg-red-500 px-6 py-2.5 font-mono text-sm uppercase tracking-widest text-white shadow-md transition-all hover:bg-red-600 hover:shadow-lg"
                  >
                    <Square size={16} strokeWidth={1.5} />
                    End Session
                  </button>
                )}
                {sessionState === "completed" && (
                  <button
                    onClick={() => {
                      setSessionState("connecting");
                      setCompletionData(null);
                      setExerciseNumber(0);
                      setElapsedSeconds(0);
                      setCurrentExercise("");
                      setCurrentPhase("Breathing");
                      setPostureNotes("");
                      clearTranscript();
                      hasAutoConnected.current = false;
                    }}
                    className="flex items-center gap-2 rounded-md bg-emerald-500 px-6 py-2.5 font-mono text-sm uppercase tracking-widest text-white shadow-md transition-all hover:bg-emerald-600 hover:shadow-lg"
                  >
                    <Play size={16} strokeWidth={1.5} />
                    New Session
                  </button>
                )}
              </div>
            </div>
          </div>

          {/* Completion summary */}
          {sessionState === "completed" && completionData && (
            <motion.div
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              className="rounded-lg border-2 border-emerald-500/30 bg-emerald-500/5 p-6"
            >
              <div className="mb-4 flex items-center gap-3">
                <Trophy size={24} className="text-emerald-400" />
                <h2 className="font-display text-xl font-bold tracking-tight">Session Complete!</h2>
              </div>
              <p className="mb-4 text-muted-foreground">
                {String(completionData.encouragement || "Great work today!")}
              </p>
              <div className="grid grid-cols-3 gap-4">
                <div className="rounded-md bg-card p-4 text-center">
                  <p className="font-mono text-2xl font-bold text-emerald-400">
                    {String(completionData.exercises_completed || exerciseNumber)}/{TOTAL_EXERCISES}
                  </p>
                  <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">Exercises</p>
                </div>
                <div className="rounded-md bg-card p-4 text-center">
                  <p className="font-mono text-2xl font-bold text-emerald-400">
                    {formatTime(elapsedSeconds)}
                  </p>
                  <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">Duration</p>
                </div>
                <div className="rounded-md bg-card p-4 text-center">
                  <p className="font-mono text-2xl font-bold text-emerald-400">
                    {String(completionData.posture_score || "—")}/100
                  </p>
                  <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">Posture</p>
                </div>
              </div>
            </motion.div>
          )}
        </div>

        {/* Right column: Progress + Transcript */}
        <div className="flex flex-col gap-6">
          {/* Session Info Card */}
          <div className="rounded-lg border border-border bg-card p-6">
            <h2 className="mb-4 font-display text-lg font-bold tracking-tight">Session Info</h2>

            {/* Phase indicator */}
            <div className={`mb-4 rounded-md border ${phaseInfo.border} ${phaseInfo.bg} p-3`}>
              <div className="flex items-center gap-2">
                <phaseInfo.icon size={16} className={phaseInfo.color} />
                <span className={`font-mono text-xs font-semibold uppercase tracking-widest ${phaseInfo.color}`}>
                  {sessionState === "active" ? (currentPhase || "Breathing") : sessionState === "welcome" ? "Warm-up" : "Ready"}
                </span>
              </div>
              {currentExercise && (
                <p className="mt-1 text-sm font-medium">{currentExercise}</p>
              )}
              {sessionState === "welcome" && !currentExercise && (
                <p className="mt-1 text-sm text-muted-foreground">Listening to your coach...</p>
              )}
            </div>

            {/* Progress */}
            <div className="mb-4">
              <div className="mb-2 flex items-center justify-between">
                <span className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">Progress</span>
                <span className="font-mono text-xs text-muted-foreground">{exerciseNumber}/{TOTAL_EXERCISES}</span>
              </div>
              <div className="h-2.5 rounded-full bg-secondary">
                <motion.div
                  animate={{ width: `${progressPercent}%` }}
                  transition={{ duration: 0.4 }}
                  className="h-full rounded-full bg-emerald-500"
                />
              </div>
            </div>

            {/* Timer */}
            <div className="flex items-center gap-2 text-muted-foreground">
              <Timer size={14} strokeWidth={1.5} />
              <span className="font-mono text-sm">{formatTime(elapsedSeconds)} / 10:00</span>
            </div>

            {/* Posture notes */}
            {postureNotes && (
              <div className="mt-4 rounded-md border border-emerald-500/20 bg-emerald-500/5 p-3">
                <p className="font-mono text-[10px] uppercase tracking-widest text-emerald-400">Coach Feedback</p>
                <p className="mt-1 text-sm text-muted-foreground">{postureNotes}</p>
              </div>
            )}

            {/* Phase pills */}
            <div className="mt-4 flex flex-wrap gap-2">
              {PHASE_INFO.map((phase) => {
                const isCurrentPhase = phase.name === currentPhase;
                const phaseIdx = PHASE_INFO.indexOf(phase);
                const currentPhaseIdx = PHASE_INFO.findIndex((p) => p.name === currentPhase);
                const isDone = phaseIdx < currentPhaseIdx;
                return (
                  <div
                    key={phase.name}
                    className={`rounded-full px-3 py-1 font-mono text-[10px] uppercase tracking-widest ${isCurrentPhase && sessionState === "active"
                      ? `${phase.bg} ${phase.border} border ${phase.color}`
                      : isDone
                        ? "bg-emerald-500/10 text-emerald-400"
                        : "bg-secondary text-muted-foreground"
                      }`}
                  >
                    {phase.name}
                  </div>
                );
              })}
            </div>
          </div>

          {/* Transcript */}
          <div className="flex flex-col rounded-lg border border-border bg-card">
            <div className="border-b border-border p-4">
              <h2 className="font-display text-lg font-bold tracking-tight">Coach</h2>
            </div>
            <div className="flex-1 space-y-3 overflow-y-auto p-4" style={{ maxHeight: "350px" }}>
              {transcript.length === 0 ? (
                <div className="py-8 text-center">
                  <Activity size={20} strokeWidth={1} className="mx-auto mb-2 text-muted-foreground/40" />
                  <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
                    {sessionState === "connecting" ? "Connecting..." : "Waiting for coach..."}
                  </p>
                </div>
              ) : (
                <AnimatePresence>
                  {transcript.map((msg, i) => (
                    <motion.div
                      key={`${msg.timestamp}-${i}`}
                      initial={{ opacity: 0, y: 6 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ duration: 0.15 }}
                      className={`rounded-md p-3 ${msg.role === "assistant"
                        ? "border-l-4 border-emerald-500 bg-emerald-500/5"
                        : "border-l-4 border-accent bg-accent/5"
                        }`}
                    >
                      <p className="mb-1 font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
                        {msg.role === "assistant" ? "Coach" : "You"}
                      </p>
                      <p className="text-sm leading-relaxed">{msg.text}</p>
                    </motion.div>
                  ))}
                </AnimatePresence>
              )}
              <div ref={transcriptEndRef} />
            </div>
          </div>
        </div>
      </div>
    </AppLayout>
  );
};

export default Exercise;
