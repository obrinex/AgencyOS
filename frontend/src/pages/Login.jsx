import { useState } from "react";
import { Navigate, useNavigate, useSearchParams, Link } from "react-router-dom";
import { motion } from "framer-motion";
import { useAuth } from "@/contexts/AuthContext";
import { formatApiError } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { InputOTP, InputOTPGroup, InputOTPSlot } from "@/components/ui/input-otp";
import { Loader2, ShieldCheck, ArrowLeft, ArrowRight, Briefcase, Gem, Building2 } from "lucide-react";
import { toast } from "sonner";

/** Two front doors, one credential.
 *
 *  A client and a founding member sign in with the same endpoint — the account
 *  already knows which it is. What the choice buys is *orientation*: someone
 *  arriving at a single unlabelled box has no way to tell whether their portal
 *  is even the thing behind it, and a member who has been told "the Circle" all
 *  the way through the application should not land on a page that says CRM.
 *
 *  ## The choice never decides anything
 *
 *  Where you land is decided by the role the server returns, not by the door
 *  you picked. Trusting the picker would mean a client could type their way
 *  into a members' route by choosing the other tab — and it would strand anyone
 *  who guessed wrong about their own account. Pick the wrong door and you still
 *  arrive in the right place; the page just says so on the way past.
 */

const DOORS = {
  client: {
    key: "client",
    label: "Client",
    icon: Briefcase,
    title: "Client portal",
    blurb: "Your projects, invoices, contracts and a direct line to your team.",
    home: "/portal",
  },
  member: {
    key: "member",
    label: "Founding Circle",
    icon: Gem,
    title: "Founding Circle",
    blurb: "Your membership, the room, the directory and your assistant.",
    home: "/founding-portal",
  },
  team: {
    key: "team",
    label: "Team",
    icon: Building2,
    title: "Obrinex CRM",
    blurb: "The agency's own operating system.",
    home: "/dashboard",
  },
};

/** Where a signed-in account actually belongs, from its role. */
function homeFor(role) {
  if (role === "client") return "/portal";
  if (role === "founding") return "/founding-portal";
  return "/dashboard";
}

const EASE = [0.16, 1, 0.3, 1];

export default function Login() {
  const { login, verify2FA, user } = useAuth();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();

  const requested = params.get("as");
  const [door, setDoor] = useState(DOORS[requested] ? requested : null);

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [requires2FA, setRequires2FA] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  if (user && user !== false) {
    return <Navigate to={homeFor(user.role)} replace />;
  }

  const choose = (key) => {
    setDoor(key);
    setError("");
    setParams({ as: key }, { replace: true });
  };

  const back = () => {
    setDoor(null);
    setError("");
    setParams({}, { replace: true });
  };

  /** Land them where their role says, and say so if it wasn't the door they chose. */
  const arrive = (account) => {
    const home = homeFor(account?.role);
    const expected = DOORS[door]?.home;
    if (expected && home !== expected) {
      toast.success(`Signed in — taking you to your ${account?.role === "founding" ? "Founding Circle" : account?.role === "client" ? "client" : "team"} portal.`);
    } else {
      toast.success("Welcome back.");
    }
    navigate(home, { replace: true });
  };

  const handleLogin = async (e) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const result = await login(email, password);
      if (result.requires2FA) {
        setRequires2FA(true);
      } else {
        // Every account used to be sent to /dashboard, which a client and a
        // member are both refused from — they bounced through a protected
        // route before landing anywhere.
        arrive(result?.user || result);
      }
    } catch (err) {
      setError(err.response?.data?.detail
        ? formatApiError(err.response.data.detail)
        : "Login request could not reach the server. Clear site data or try another browser.");
    } finally {
      setLoading(false);
    }
  };

  const handleVerify2FA = async (e) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const result = await verify2FA(code);
      arrive(result?.user || result);
    } catch (err) {
      setError(err.response?.data?.detail
        ? formatApiError(err.response.data.detail)
        : "Verification request could not reach the server. Clear site data or try another browser.");
    } finally {
      setLoading(false);
    }
  };

  const active = DOORS[door];

  return (
    <div className="relative flex min-h-[100dvh] w-full items-center justify-center px-4 py-10"
         data-testid="login-page">
      <div className="obx-aurora pointer-events-none absolute inset-0" />

      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, ease: EASE }}
        className="relative z-10 w-full max-w-sm"
      >
        <Link to="/" className="mb-8 flex flex-col items-center">
          <div className="obx-holo obx-glass relative mb-4 flex h-12 w-12 items-center justify-center overflow-hidden rounded-2xl">
            <span className="relative z-10 font-display text-lg font-bold">O</span>
          </div>
          <h1 className="font-display text-xl font-bold tracking-tight">
            {active ? active.title : "Obrinex"}
          </h1>
          <p className="mt-1 font-mono text-[10px] uppercase tracking-[0.24em] text-graphite">
            {active ? "Sign in" : "Choose your door"}
          </p>
        </Link>

        {/* Enter-only, no AnimatePresence: the panel that leaves just unmounts.
            An exit animation here can only finish if animation frames are
            running, and a door chooser that leaves a blank card when they are
            not is a worse failure than a missing fade. */}
        <div>
          {!door ? (
            <motion.div
              key="chooser"
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.34, ease: EASE }}
              className="space-y-2.5"
              data-testid="login-chooser"
            >
              {[DOORS.client, DOORS.member].map((d, i) => (
                <motion.button
                  key={d.key}
                  initial={{ opacity: 0, y: 12 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: 0.06 + i * 0.07, ease: EASE }}
                  onClick={() => choose(d.key)}
                  data-testid={`login-as-${d.key}`}
                  className="obx-glass obx-lift obx-sheen group flex w-full items-center gap-3.5 rounded-2xl p-4 text-left"
                >
                  <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-primary/12 text-primary ring-1 ring-primary/25">
                    <d.icon className="h-4 w-4" />
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block text-sm font-medium">{d.label}</span>
                    <span className="mt-0.5 block text-xs leading-snug text-graphite">{d.blurb}</span>
                  </span>
                  <ArrowRight className="h-4 w-4 shrink-0 text-carbon transition-transform group-hover:translate-x-0.5 group-hover:text-primary" />
                </motion.button>
              ))}

              {/* Staff still need a way in. Quiet, because it is not for the
                  people this page is mostly for. */}
              <button
                onClick={() => choose("team")}
                data-testid="login-as-team"
                className="w-full pt-2 text-center text-xs text-carbon transition-colors hover:text-foreground"
              >
                I work at Obrinex →
              </button>
            </motion.div>
          ) : (
            <motion.div
              key="form"
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.34, ease: EASE }}
            >
              <div className="obx-glass rounded-2xl p-6">
                {!requires2FA ? (
                  <form onSubmit={handleLogin} className="space-y-4" data-testid="login-form">
                    <div className="space-y-1.5">
                      <Label htmlFor="email">Email</Label>
                      <Input
                        id="email"
                        data-testid="login-email-input"
                        type="email"
                        autoComplete="email"
                        value={email}
                        onChange={(e) => setEmail(e.target.value)}
                        required
                        autoFocus
                        className="bg-surface-2 border-white/10"
                      />
                    </div>
                    <div className="space-y-1.5">
                      <Label htmlFor="password">Password</Label>
                      <Input
                        id="password"
                        data-testid="login-password-input"
                        type="password"
                        autoComplete="current-password"
                        value={password}
                        onChange={(e) => setPassword(e.target.value)}
                        required
                        className="bg-surface-2 border-white/10"
                      />
                    </div>
                    {error && <p data-testid="login-error" className="text-sm text-danger">{error}</p>}
                    <Button data-testid="login-submit-button" type="submit" disabled={loading} className="w-full">
                      {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : "Sign in"}
                    </Button>
                  </form>
                ) : (
                  <form onSubmit={handleVerify2FA} className="space-y-4" data-testid="twofa-form">
                    <div className="mb-2 flex flex-col items-center gap-2">
                      <ShieldCheck className="h-6 w-6 text-primary" />
                      <p className="text-center text-sm text-ash">
                        Enter the 6-digit code from your authenticator app
                      </p>
                    </div>
                    <div className="flex justify-center">
                      <InputOTP maxLength={6} value={code} onChange={setCode} data-testid="twofa-code-input">
                        <InputOTPGroup>
                          {[0, 1, 2, 3, 4, 5].map((i) => (
                            <InputOTPSlot key={i} index={i} className="border-white/10 bg-surface-2" />
                          ))}
                        </InputOTPGroup>
                      </InputOTP>
                    </div>
                    {error && <p data-testid="twofa-error" className="text-center text-sm text-danger">{error}</p>}
                    <Button data-testid="twofa-submit-button" type="submit" disabled={loading || code.length < 6} className="w-full">
                      {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : "Verify"}
                    </Button>
                  </form>
                )}
              </div>

              {!requires2FA && (
                <button
                  onClick={back}
                  data-testid="login-back"
                  className="mt-4 flex w-full items-center justify-center gap-1.5 text-xs text-carbon transition-colors hover:text-foreground"
                >
                  <ArrowLeft className="h-3 w-3" /> Not you? Choose a different door
                </button>
              )}
            </motion.div>
          )}
        </div>

        <p className="mt-8 text-center font-mono text-[10px] uppercase tracking-[0.2em] text-carbon">
          Agency Operating System · Est. 2026
        </p>
      </motion.div>
    </div>
  );
}
