import { FileText, Camera, Upload, CheckCircle2, Clock } from "lucide-react";
import AppLayout from "@/components/AppLayout";

const prescriptions = [
  {
    doctor: "Dr. Sharma",
    date: "March 5, 2026",
    medications: ["Metformin 500mg - 2x daily", "Lisinopril 10mg - 1x daily"],
    status: "active",
  },
  {
    doctor: "Dr. Patel",
    date: "Feb 20, 2026",
    medications: ["Atorvastatin 20mg - 1x nightly", "Aspirin 81mg - 1x daily"],
    status: "active",
  },
  {
    doctor: "Dr. Gupta",
    date: "Jan 10, 2026",
    medications: ["Omeprazole 20mg - 1x daily"],
    status: "completed",
  },
];

const Prescriptions = () => {
  return (
    <AppLayout>
      <div className="mb-12">
        <h1 className="font-display text-5xl font-bold tracking-tight lg:text-7xl">
          Prescrip&shy;
          <br />
          <em className="text-primary">tions</em>
        </h1>
        <div className="rule-thick mt-6 mb-8 max-w-32" />
        <p className="max-w-lg text-lg text-muted-foreground">
          Scan or upload prescriptions for automatic medication extraction
        </p>
      </div>

      {/* Scan area */}
      <div className="mb-8 flex flex-col items-start justify-between rounded-lg border border-border bg-card p-6 sm:flex-row sm:items-center">
        <div className="mb-4 sm:mb-0">
          <h2 className="font-display text-xl font-bold tracking-tight">Scan New Prescription</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Take a photo and our AI will extract all medications
          </p>
        </div>
        <div className="flex gap-3">
          <button className="flex items-center gap-2 rounded-md bg-primary px-6 py-3 font-mono text-xs uppercase tracking-widest text-primary-foreground shadow-md transition-all hover:shadow-lg">
            <Camera size={14} strokeWidth={1.5} />
            Scan
          </button>
          <button className="flex items-center gap-2 rounded-md border-2 border-border px-4 py-3 font-mono text-xs uppercase tracking-widest transition-colors hover:bg-secondary">
            <Upload size={14} strokeWidth={1.5} />
            Upload
          </button>
        </div>
      </div>

      {/* List */}
      <div className="space-y-4">
        {prescriptions.map((rx, i) => (
          <div
            key={i}
            className="rounded-lg border border-border bg-card p-6 transition-colors hover:border-primary/30"
          >
            <div className="mb-4 flex items-center justify-between">
              <div className="flex items-center gap-4">
                <div className="rounded-full bg-primary/10 p-2.5 text-primary">
                  <FileText size={20} strokeWidth={1.5} />
                </div>
                <div>
                  <p className="font-display text-lg font-semibold">{rx.doctor}</p>
                  <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">{rx.date}</p>
                </div>
              </div>
              <span className={`flex items-center gap-1.5 rounded-full px-3 py-1 font-mono text-[10px] uppercase tracking-widest ${
                rx.status === "active"
                  ? "bg-success/10 text-success"
                  : "bg-secondary text-muted-foreground"
              }`}>
                {rx.status === "active" ? (
                  <CheckCircle2 size={12} strokeWidth={1.5} />
                ) : (
                  <Clock size={12} strokeWidth={1.5} />
                )}
                {rx.status}
              </span>
            </div>
            <div className="flex flex-wrap gap-2">
              {rx.medications.map((med) => (
                <span
                  key={med}
                  className="rounded-md bg-secondary px-3 py-1.5 font-mono text-xs"
                >
                  {med}
                </span>
              ))}
            </div>
          </div>
        ))}
      </div>
    </AppLayout>
  );
};

export default Prescriptions;
