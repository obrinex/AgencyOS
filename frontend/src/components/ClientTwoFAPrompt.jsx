import { useEffect, useState } from "react";
import { ShieldCheck, X, Loader2 } from "lucide-react";
import { toast } from "sonner";
import api, { formatApiError } from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";
import { InputOTP, InputOTPGroup, InputOTPSlot } from "@/components/ui/input-otp";

// The provisioning URI as a QR image — same approach the crypto-payment page
// uses, so no extra dependency.
const qrUrl = (data) =>
  `https://api.qrserver.com/v1/create-qr-code/?size=190x190&bgcolor=24-24-26&color=244-244-245&data=${encodeURIComponent(data)}`;

/** A nudge for clients who haven't turned on 2FA.
 *
 *  ## It used to take the whole portal hostage
 *
 *  This was a Radix modal, opened automatically on every single load for any
 *  client without 2FA. A Radix modal sets `pointer-events: none` on `<body>`
 *  and lays an overlay at z-50 over everything, so until it was dismissed the
 *  portal was inert: the bottom navigation, the More button and the sign-out
 *  control were all underneath it and none of them responded. It was reported
 *  as "the More button doesn't work" and "there's no way to log out", which is
 *  exactly what it looked like from the outside.
 *
 *  It is a card now. Nothing behind it is blocked, nothing is covered but the
 *  corner it occupies, and it can be ignored indefinitely.
 *
 *  ## And it only asks once
 *
 *  Dismissal was component state, so "Maybe later" lasted until the next
 *  reload — which is not "one per session" by any reading. The choice is
 *  remembered per user id, and the moment 2FA is actually enabled the prompt
 *  removes itself and the stored flag stops mattering.
 */
const dismissKey = (id) => `obx-2fa-dismissed:${id}`;

export default function ClientTwoFAPrompt({ suspended = false }) {
  const { user, setUser } = useAuth();
  const [dismissed, setDismissed] = useState(true);
  const [open, setOpen] = useState(false);
  const [setupData, setSetupData] = useState(null);
  const [code, setCode] = useState("");
  const [enabling, setEnabling] = useState(false);

  // Read the stored choice once the user is known. Starts dismissed so the
  // card can never flash on screen before we know whether it was declined.
  useEffect(() => {
    if (!user?.id) return;
    try {
      setDismissed(window.localStorage.getItem(dismissKey(user.id)) === "1");
    } catch {
      setDismissed(false);
    }
  }, [user?.id]);

  const shouldShow =
    !suspended && !!user && user.role === "client" && !user.two_fa_enabled && !dismissed;

  useEffect(() => {
    if (shouldShow && open && !setupData) {
      api.post("/auth/2fa/setup")
        .then((r) => setSetupData(r.data))
        .catch(() => { /* leave it empty; reopening retries */ });
    }
  }, [shouldShow, open, setupData]);

  const decline = () => {
    setDismissed(true);
    try { window.localStorage.setItem(dismissKey(user.id), "1"); } catch { /* private mode */ }
  };

  const enable = async () => {
    setEnabling(true);
    try {
      await api.post("/auth/2fa/enable", { code });
      setUser({ ...user, two_fa_enabled: true });
      toast.success("Two-factor authentication is on. Your account is protected.");
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail)
        || "That code didn't match — enter the current one from your app.");
    } finally {
      setEnabling(false);
    }
  };

  if (!shouldShow) return null;

  return (
    <div
      data-testid="client-2fa-prompt"
      className="pb-safe pointer-events-none fixed inset-x-0 bottom-0 z-30 flex justify-center px-4 pb-4 md:inset-x-auto md:right-6 md:justify-end"
    >
      <div className="obx-glass pointer-events-auto w-full max-w-sm overflow-hidden rounded-2xl">
        <div className="flex items-start gap-3 p-4">
          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-success/12 text-success ring-1 ring-success/25">
            <ShieldCheck className="h-4 w-4" />
          </span>
          <div className="min-w-0 flex-1">
            <p className="text-sm font-medium">Secure your account</p>
            <p className="mt-1 text-xs leading-relaxed text-graphite">
              Two-factor authentication takes about a minute and keeps your account safe
              even if your password is ever exposed.
            </p>
          </div>
          <button
            onClick={decline}
            aria-label="Dismiss"
            data-testid="client-2fa-later"
            className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg text-carbon transition-colors hover:text-foreground"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {!open ? (
          <div className="flex gap-2 px-4 pb-4">
            <button
              onClick={() => setOpen(true)}
              data-testid="client-2fa-open"
              className="flex-1 rounded-lg bg-primary px-3 py-2 text-xs font-medium text-background"
            >
              Set it up
            </button>
            <button
              onClick={decline}
              className="rounded-lg px-3 py-2 text-xs text-graphite transition-colors hover:text-foreground"
            >
              Not now
            </button>
          </div>
        ) : (
          <div className="border-t border-white/10 p-4">
            <ol className="space-y-1 text-xs text-graphite">
              <li>1. Open your authenticator app.</li>
              <li>2. Scan the code, then enter the six digits.</li>
            </ol>
            {setupData ? (
              <div className="mt-3 flex flex-col items-center gap-3">
                <img
                  src={qrUrl(setupData.uri)}
                  alt="Authenticator QR code"
                  width={150}
                  height={150}
                  className="rounded-lg border border-white/10 bg-surface-2"
                />
                <p className="break-all rounded bg-surface-2 p-2 text-center font-mono text-[10px]"
                   data-testid="client-2fa-secret">
                  {setupData.secret}
                </p>
                <InputOTP maxLength={6} value={code} onChange={setCode} data-testid="client-2fa-code">
                  <InputOTPGroup>
                    {[0, 1, 2, 3, 4, 5].map((i) => (
                      <InputOTPSlot key={i} index={i} className="border-white/10 bg-surface-2" />
                    ))}
                  </InputOTPGroup>
                </InputOTP>
                <button
                  onClick={enable}
                  disabled={enabling || code.length < 6}
                  data-testid="client-2fa-enable"
                  className="flex w-full items-center justify-center gap-2 rounded-lg bg-primary px-3 py-2 text-xs font-medium text-background disabled:opacity-40"
                >
                  {enabling && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
                  Turn on 2FA
                </button>
              </div>
            ) : (
              <p className="py-6 text-center text-xs text-graphite">Preparing your setup code…</p>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
