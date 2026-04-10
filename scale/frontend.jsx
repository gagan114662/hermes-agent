import { useState } from "react";

const WORKERS = [
  {
    id: "sdr",
    name: "Alex",
    role: "Sales Development Rep",
    emoji: "🎯",
    color: "from-violet-500 to-purple-600",
    tagline: "Finds leads. Books meetings. Never sleeps.",
    schedule: "Every morning at 8am",
    scheduleDetail: "Sends you 5 qualified leads with personalized outreach drafted",
    tools: ["Web research", "LinkedIn signals", "Email outreach", "Prospect tracking"],
    example: "\"Found 5 companies that just opened warehouses + hiring logistics heads. Drafted outreach for each. 2 replies already.\"",
  },
  {
    id: "content",
    name: "Sam",
    role: "Content & Growth Manager",
    emoji: "✍️",
    color: "from-pink-500 to-rose-600",
    tagline: "Writes, posts, grows. Every single day.",
    schedule: "Every Monday at 9am",
    scheduleDetail: "Delivers a week of content — blog, LinkedIn, Twitter, email",
    tools: ["Trend monitoring", "Content writing", "Social posting", "Image generation"],
    example: "\"Spotted 3 trending AI topics in your space. Drafted a LinkedIn post, Twitter thread, and newsletter. Ready to approve.\"",
  },
  {
    id: "support",
    name: "Jordan",
    role: "Customer Support Specialist",
    emoji: "💬",
    color: "from-cyan-500 to-blue-600",
    tagline: "Every customer feels heard. Always.",
    schedule: "Every evening at 5pm",
    scheduleDetail: "Daily digest: tickets resolved, escalations, recurring issues",
    tools: ["Customer memory", "Conversation history", "Multi-language", "Escalation routing"],
    example: "\"Handled 23 messages today. 21 resolved. 2 escalated to you (refund requests). Same shipping question came up 4x — suggest adding it to FAQ.\"",
  },
  {
    id: "research",
    name: "Casey",
    role: "Research & Intelligence Analyst",
    emoji: "🔍",
    color: "from-amber-500 to-orange-600",
    tagline: "Intel that actually changes your decisions.",
    schedule: "Every morning at 7am",
    scheduleDetail: "Morning brief: competitor moves, market shifts, what matters today",
    tools: ["Web research", "Reddit & Twitter", "YouTube analysis", "Data synthesis"],
    example: "\"Competitor just raised $8M. Here's what changed in their product, who they're hiring, and 3 things you should do in response.\"",
  },
  {
    id: "ops",
    name: "Morgan",
    role: "Operations & Automation Manager",
    emoji: "⚙️",
    color: "from-emerald-500 to-green-600",
    tagline: "If it happens twice, it should be automated.",
    schedule: "Every weekday at 6am",
    scheduleDetail: "Ops check: system status, calendar prep, inbox triage, reports",
    tools: ["Gmail", "Calendar", "Google Sheets", "Terminal", "File management"],
    example: "\"Good morning. 3 urgent emails flagged. Your 2pm meeting needs a brief — drafted it. Monthly report ready in Sheets.\"",
  },
];

const PRICING = [
  { name: "Starter", price: 99, workers: 1, desc: "One AI worker, fully managed" },
  { name: "Team", price: 249, workers: 3, desc: "Three workers, perfect for small teams", popular: true },
  { name: "Scale", price: 599, workers: "Unlimited", desc: "As many workers as you need" },
];

function WorkerCard({ worker, onHire }) {
  const [hovered, setHovered] = useState(false);
  return (
    <div
      className="bg-white rounded-2xl border border-gray-100 shadow-sm overflow-hidden cursor-pointer transition-all duration-200 hover:shadow-lg hover:-translate-y-1"
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      onClick={() => onHire(worker)}
    >
      <div className={`bg-gradient-to-r ${worker.color} p-6 text-white`}>
        <div className="flex items-center justify-between mb-3">
          <span className="text-4xl">{worker.emoji}</span>
          <span className="bg-white bg-opacity-20 text-white text-xs px-3 py-1 rounded-full font-medium">
            {worker.role}
          </span>
        </div>
        <h3 className="text-2xl font-bold">{worker.name}</h3>
        <p className="text-white text-opacity-90 text-sm mt-1">{worker.tagline}</p>
      </div>
      <div className="p-6">
        <div className="bg-gray-50 rounded-xl p-4 mb-4">
          <div className="flex items-center gap-2 mb-1">
            <span className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Proactive Schedule</span>
          </div>
          <p className="text-sm font-medium text-gray-800">{worker.schedule}</p>
          <p className="text-xs text-gray-500 mt-0.5">{worker.scheduleDetail}</p>
        </div>
        <div className="flex flex-wrap gap-2 mb-4">
          {worker.tools.map(t => (
            <span key={t} className="text-xs bg-gray-100 text-gray-600 px-2.5 py-1 rounded-full">{t}</span>
          ))}
        </div>
        <div className="bg-gray-50 rounded-xl p-3 border-l-4 border-gray-300">
          <p className="text-xs text-gray-500 italic">{worker.example}</p>
        </div>
        <button
          className={`mt-4 w-full py-2.5 rounded-xl text-sm font-semibold transition-all duration-200 bg-gradient-to-r ${worker.color} text-white hover:opacity-90`}
        >
          Hire {worker.name} →
        </button>
      </div>
    </div>
  );
}

function HireModal({ worker, onClose }) {
  const [step, setStep] = useState(1);
  const [form, setForm] = useState({ businessName: "", businessInfo: "", telegramToken: "" });
  const [done, setDone] = useState(false);

  if (!worker) return null;

  const handleSubmit = () => {
    setDone(true);
  };

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4" onClick={onClose}>
      <div className="bg-white rounded-2xl w-full max-w-lg shadow-2xl" onClick={e => e.stopPropagation()}>
        {done ? (
          <div className="p-8 text-center">
            <div className={`w-16 h-16 rounded-2xl bg-gradient-to-r ${worker.color} flex items-center justify-center text-3xl mx-auto mb-4`}>
              {worker.emoji}
            </div>
            <h2 className="text-2xl font-bold text-gray-900 mb-2">{worker.name} is ready!</h2>
            <p className="text-gray-500 mb-6">
              Your AI worker is being deployed. You'll receive a welcome message on Telegram in about 30 seconds.
            </p>
            <div className="bg-gray-50 rounded-xl p-4 text-left mb-6">
              <p className="text-sm font-medium text-gray-700 mb-1">What happens next:</p>
              <ul className="text-sm text-gray-500 space-y-1">
                <li>✅ {worker.name} joins your Telegram</li>
                <li>✅ First {worker.schedule.toLowerCase()} brief scheduled</li>
                <li>✅ Business knowledge loaded</li>
              </ul>
            </div>
            <button onClick={onClose} className={`w-full py-3 rounded-xl font-semibold text-white bg-gradient-to-r ${worker.color}`}>
              Go to Dashboard
            </button>
          </div>
        ) : (
          <>
            <div className={`bg-gradient-to-r ${worker.color} p-6 text-white rounded-t-2xl`}>
              <div className="flex items-center gap-3">
                <span className="text-3xl">{worker.emoji}</span>
                <div>
                  <h2 className="text-xl font-bold">Hire {worker.name}</h2>
                  <p className="text-white text-opacity-80 text-sm">{worker.role}</p>
                </div>
              </div>
              <div className="flex gap-2 mt-4">
                {[1, 2].map(s => (
                  <div key={s} className={`h-1.5 flex-1 rounded-full ${step >= s ? "bg-white" : "bg-white bg-opacity-30"}`} />
                ))}
              </div>
            </div>

            <div className="p-6">
              {step === 1 && (
                <div className="space-y-4">
                  <h3 className="font-semibold text-gray-900">Tell {worker.name} about your business</h3>
                  <div>
                    <label className="text-sm font-medium text-gray-700 block mb-1.5">Business name</label>
                    <input
                      className="w-full border border-gray-200 rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-violet-500"
                      placeholder="e.g. Acme Corp"
                      value={form.businessName}
                      onChange={e => setForm({...form, businessName: e.target.value})}
                    />
                  </div>
                  <div>
                    <label className="text-sm font-medium text-gray-700 block mb-1.5">What does your business do? Who are your customers?</label>
                    <textarea
                      className="w-full border border-gray-200 rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-violet-500 resize-none"
                      rows={4}
                      placeholder={`e.g. We sell B2B SaaS to logistics companies. Target: VP Operations at companies with 50-500 employees. Our ICP is growing fast and needs to automate warehouse ops.`}
                      value={form.businessInfo}
                      onChange={e => setForm({...form, businessInfo: e.target.value})}
                    />
                  </div>
                  <button
                    onClick={() => setStep(2)}
                    disabled={!form.businessName || !form.businessInfo}
                    className={`w-full py-3 rounded-xl font-semibold text-white bg-gradient-to-r ${worker.color} disabled:opacity-40`}
                  >
                    Continue →
                  </button>
                </div>
              )}

              {step === 2 && (
                <div className="space-y-4">
                  <h3 className="font-semibold text-gray-900">Connect {worker.name} to Telegram</h3>
                  <div className="bg-blue-50 rounded-xl p-4 text-sm text-blue-700">
                    <p className="font-medium mb-2">Create a Telegram bot in 30 seconds:</p>
                    <ol className="space-y-1 list-decimal list-inside text-blue-600">
                      <li>Open Telegram → search <span className="font-mono bg-blue-100 px-1 rounded">@BotFather</span></li>
                      <li>Send <span className="font-mono bg-blue-100 px-1 rounded">/newbot</span></li>
                      <li>Choose a name for {worker.name}</li>
                      <li>Copy the token it gives you</li>
                    </ol>
                  </div>
                  <div>
                    <label className="text-sm font-medium text-gray-700 block mb-1.5">Bot token</label>
                    <input
                      className="w-full border border-gray-200 rounded-xl px-4 py-2.5 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-violet-500"
                      placeholder="1234567890:AAF-xxxxxxxxxxxxxxxxxxxxxxxxxxxx"
                      value={form.telegramToken}
                      onChange={e => setForm({...form, telegramToken: e.target.value})}
                    />
                  </div>
                  <div className="flex gap-3">
                    <button onClick={() => setStep(1)} className="flex-1 py-3 rounded-xl font-semibold text-gray-600 border border-gray-200">
                      ← Back
                    </button>
                    <button
                      onClick={handleSubmit}
                      disabled={!form.telegramToken}
                      className={`flex-1 py-3 rounded-xl font-semibold text-white bg-gradient-to-r ${worker.color} disabled:opacity-40`}
                    >
                      Deploy {worker.name} 🚀
                    </button>
                  </div>
                </div>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
}

function Dashboard({ workers, onHire }) {
  const activeWorkers = [
    { ...WORKERS[0], status: "active", lastAction: "Sent 5 leads + outreach drafts", time: "8:03am today", messages: 42 },
  ];

  return (
    <div className="max-w-5xl mx-auto">
      <div className="flex items-center justify-between mb-8">
        <div>
          <h2 className="text-2xl font-bold text-gray-900">Your AI Workers</h2>
          <p className="text-gray-500 text-sm mt-0.5">{activeWorkers.length} active · next action in 4h 12m</p>
        </div>
        <button
          onClick={() => onHire(null)}
          className="bg-gray-900 text-white px-5 py-2.5 rounded-xl text-sm font-semibold hover:bg-gray-700 transition-colors"
        >
          + Hire Worker
        </button>
      </div>

      {/* Active worker cards */}
      {activeWorkers.map(w => (
        <div key={w.id} className="bg-white rounded-2xl border border-gray-100 shadow-sm p-6 mb-4">
          <div className="flex items-start justify-between">
            <div className="flex items-center gap-4">
              <div className={`w-14 h-14 rounded-2xl bg-gradient-to-r ${w.color} flex items-center justify-center text-2xl`}>
                {w.emoji}
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <h3 className="font-bold text-gray-900 text-lg">{w.name}</h3>
                  <span className="bg-green-100 text-green-700 text-xs px-2.5 py-0.5 rounded-full font-medium">● Active</span>
                </div>
                <p className="text-gray-500 text-sm">{w.role}</p>
              </div>
            </div>
            <div className="text-right">
              <p className="text-2xl font-bold text-gray-900">{w.messages}</p>
              <p className="text-gray-400 text-xs">messages handled</p>
            </div>
          </div>
          <div className="mt-4 bg-gray-50 rounded-xl p-4">
            <div className="flex items-center gap-2">
              <span className="text-green-500 text-sm">✓</span>
              <p className="text-sm text-gray-700 font-medium">{w.lastAction}</p>
              <span className="text-gray-400 text-xs ml-auto">{w.time}</span>
            </div>
          </div>
          <div className="mt-3 flex items-center gap-3">
            <div className="flex-1 bg-gray-100 rounded-full h-1.5">
              <div className={`h-1.5 rounded-full bg-gradient-to-r ${w.color}`} style={{width: "68%"}} />
            </div>
            <span className="text-xs text-gray-500">Next brief in 4h 12m</span>
          </div>
        </div>
      ))}

      {/* Hire more */}
      <div className="border-2 border-dashed border-gray-200 rounded-2xl p-8 text-center">
        <p className="text-gray-500 text-sm mb-4">Add another AI worker to your team</p>
        <div className="flex flex-wrap gap-3 justify-center">
          {WORKERS.filter(w => w.id !== "sdr").map(w => (
            <button
              key={w.id}
              onClick={() => onHire(w)}
              className="flex items-center gap-2 bg-white border border-gray-200 rounded-xl px-4 py-2.5 text-sm font-medium text-gray-700 hover:border-gray-400 transition-colors"
            >
              <span>{w.emoji}</span> {w.name} · {w.role}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

export default function App() {
  const [page, setPage] = useState("landing");
  const [selectedWorker, setSelectedWorker] = useState(null);
  const [showModal, setShowModal] = useState(false);

  const handleHire = (worker) => {
    setSelectedWorker(worker || WORKERS[0]);
    setShowModal(true);
  };

  return (
    <div className="min-h-screen bg-gray-50 font-sans">
      {/* Nav */}
      <nav className="bg-white border-b border-gray-100 sticky top-0 z-40">
        <div className="max-w-6xl mx-auto px-6 h-14 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="w-7 h-7 rounded-lg bg-gray-900 flex items-center justify-center">
              <span className="text-white text-xs font-bold">H</span>
            </div>
            <span className="font-bold text-gray-900">Hermes</span>
            <span className="text-gray-400 text-sm ml-1">AI Workers</span>
          </div>
          <div className="flex items-center gap-4">
            <button
              onClick={() => setPage("landing")}
              className={`text-sm font-medium ${page === "landing" ? "text-gray-900" : "text-gray-500 hover:text-gray-900"}`}
            >
              Workers
            </button>
            <button
              onClick={() => setPage("dashboard")}
              className={`text-sm font-medium ${page === "dashboard" ? "text-gray-900" : "text-gray-500 hover:text-gray-900"}`}
            >
              Dashboard
            </button>
            <button
              onClick={() => handleHire(WORKERS[0])}
              className="bg-gray-900 text-white px-4 py-1.5 rounded-lg text-sm font-semibold hover:bg-gray-700 transition-colors"
            >
              Hire a Worker
            </button>
          </div>
        </div>
      </nav>

      {page === "landing" && (
        <div>
          {/* Hero */}
          <div className="max-w-6xl mx-auto px-6 pt-20 pb-16 text-center">
            <div className="inline-flex items-center gap-2 bg-violet-50 border border-violet-100 text-violet-700 text-xs font-semibold px-3 py-1.5 rounded-full mb-6">
              <span className="w-1.5 h-1.5 rounded-full bg-violet-500 animate-pulse"></span>
              AI workers that actually work
            </div>
            <h1 className="text-5xl font-extrabold text-gray-900 leading-tight mb-4">
              Hire an AI worker.<br />
              <span className="bg-gradient-to-r from-violet-600 to-purple-600 bg-clip-text text-transparent">
                Get results by tomorrow.
              </span>
            </h1>
            <p className="text-gray-500 text-xl max-w-xl mx-auto mb-8">
              Each worker has a name, a job, a schedule, and memory that grows over time. Deploy in minutes on Telegram.
            </p>
            <div className="flex items-center justify-center gap-4">
              <button
                onClick={() => handleHire(WORKERS[0])}
                className="bg-gray-900 text-white px-7 py-3.5 rounded-xl font-semibold hover:bg-gray-700 transition-colors"
              >
                Hire your first worker →
              </button>
              <button
                onClick={() => setPage("dashboard")}
                className="text-gray-600 font-medium hover:text-gray-900"
              >
                See dashboard
              </button>
            </div>
            <p className="text-gray-400 text-sm mt-4">$99/month · Cancel anytime · Runs on Telegram</p>
          </div>

          {/* Worker grid */}
          <div className="max-w-6xl mx-auto px-6 pb-20">
            <h2 className="text-2xl font-bold text-gray-900 text-center mb-2">Meet your team</h2>
            <p className="text-gray-500 text-center mb-10">Five AI workers. Each one does a specific job, proactively, every day.</p>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
              {WORKERS.map(w => <WorkerCard key={w.id} worker={w} onHire={handleHire} />)}
            </div>
          </div>

          {/* Pricing */}
          <div className="bg-white border-t border-gray-100 py-20">
            <div className="max-w-4xl mx-auto px-6">
              <h2 className="text-2xl font-bold text-gray-900 text-center mb-2">Simple pricing</h2>
              <p className="text-gray-500 text-center mb-10">Pay per worker. Cancel anytime.</p>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                {PRICING.map(p => (
                  <div key={p.name} className={`rounded-2xl p-6 border-2 ${p.popular ? "border-violet-500 bg-violet-50" : "border-gray-100 bg-white"}`}>
                    {p.popular && (
                      <span className="bg-violet-500 text-white text-xs font-semibold px-3 py-1 rounded-full mb-4 block w-fit">Most popular</span>
                    )}
                    <h3 className="font-bold text-gray-900 text-lg">{p.name}</h3>
                    <div className="my-3">
                      <span className="text-4xl font-extrabold text-gray-900">${p.price}</span>
                      <span className="text-gray-400 text-sm">/month</span>
                    </div>
                    <p className="text-gray-500 text-sm mb-4">{p.desc}</p>
                    <p className="text-gray-700 font-medium text-sm mb-4">
                      {typeof p.workers === "number" ? `${p.workers} AI worker${p.workers > 1 ? "s" : ""}` : "Unlimited workers"}
                    </p>
                    <button
                      onClick={() => handleHire(WORKERS[0])}
                      className={`w-full py-2.5 rounded-xl font-semibold text-sm ${p.popular ? "bg-violet-600 text-white hover:bg-violet-700" : "bg-gray-900 text-white hover:bg-gray-700"} transition-colors`}
                    >
                      Get started →
                    </button>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}

      {page === "dashboard" && (
        <div className="max-w-6xl mx-auto px-6 py-10">
          <Dashboard onHire={handleHire} />
        </div>
      )}

      {showModal && (
        <HireModal
          worker={selectedWorker}
          onClose={() => setShowModal(false)}
        />
      )}
    </div>
  );
}
