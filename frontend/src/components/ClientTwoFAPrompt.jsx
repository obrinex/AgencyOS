import { useEffect, useState } from "react";
import { ShieldCheck } from "lucide-react";
import { toast } from "sonner";
import api, { formatApiError } from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { InputOTP, InputOTPGroup, InputOTPSlot } from "@/components/ui/input-otp";

// Same QR approach the crypto-payment page uses (no extra dependency): render
// the otpauth:// provisioning URI as an image the client scans in Google
// Authenticator.
const qrUrl = (data) =>
  `https://api.qrserver.com/v1/create-qr-code/?size=190x190&bgcolor=24-24-26&color=244-244-245&data=${encodeURIComponent(data)}`;

// A gentle, one-per-session nudge for clients who haven't turned on 2FA. It
// drives the existing /auth/2fa/{setup,enable} flow, and the moment 2FA is on it
// removes itself: enabling flips `two_fa_enabled` in the auth context, the
// show-condition goes false, and the component returns null.
export default function ClientTwoFAPrompt() {
  const { user, setUser } = useAuth();
  const [dismissed, setDismissed] = useState(false);
  const [setupData, setSetupData] = useState(null);
  const [code, setCode] = useState("");
  const [enabling, setEnabling] = useState(false);

  const shouldShow =
    !!user && user.role === "client" && !user.two_fa_enabled && !dismissed;

  useEffect(() => {
    // Fetch a fresh secret + URI once, when we've decided to show the prompt.
    if (shouldShow && !setupData) {
      api.post("/auth/2fa/setup")
        .then((r) => setSetupData(r.data))
        .catch(() => { /* leave the code area empty; reopening retries */ });
    }
  }, [shouldShow, setupData]);

  const enable = async () => {
    setEnabling(true);
    try {
      await api.post("/auth/2fa/enable", { code });
      // Flip the flag locally so the prompt disappears the instant it's set up,
      // with no reload and no refetch.
      setUser({ ...user, two_fa_enabled: true });
      toast.success("Two-factor authentication is on. Your account is protected.");
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail) ||
        "That code didn't match — enter the current one from your app.");
    } finally {
      setEnabling(false);
    }
  };

  if (!shouldShow) return null;

  return (
    <Dialog open onOpenChange={(o) => { if (!o) setDismissed(true); }}>
      <DialogContent className="bg-surface-1 border-white/10" data-testid="client-2fa-prompt">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <ShieldCheck className="h-5 w-5 text-emerald-400" /> Secure your account
          </DialogTitle>
          <DialogDescription>
            Turn on two-factor authentication with Google Authenticator (or any
            authenticator app). It takes about a minute and keeps your account safe
            even if your password is ever exposed.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <ol className="text-sm text-ash space-y-1 list-decimal list-inside">
            <li>Open Google Authenticator on your phone.</li>
            <li>Tap <b>+</b> → <b>Scan a QR code</b>.</li>
            <li>Scan the code below, then enter the 6-digit code it shows.</li>
          </ol>

          {setupData ? (
            <div className="flex flex-col items-center gap-3">
              <img src={qrUrl(setupData.uri)} alt="Authenticator QR code"
                width={190} height={190}
                className="rounded-lg border border-white/10 bg-surface-2" />
              <div className="text-center">
                <p className="text-[10px] uppercase tracking-wider text-graphite">Can't scan? Enter this key</p>
                <p className="font-mono text-xs break-all bg-surface-2 rounded p-2 mt-1"
                   data-testid="client-2fa-secret">{setupData.secret}</p>
              </div>
              <InputOTP maxLength={6} value={code} onChange={setCode} data-testid="client-2fa-code">
                <InputOTPGroup>
                  {[0, 1, 2, 3, 4, 5].map((i) => (
                    <InputOTPSlot key={i} index={i} className="border-white/10 bg-surface-2" />
                  ))}
                </InputOTPGroup>
              </InputOTP>
            </div>
          ) : (
            <p className="text-sm text-graphite text-center py-6">Preparing your setup code…</p>
          )}
        </div>

        <DialogFooter className="gap-2 sm:gap-2">
          <Button variant="ghost" onClick={() => setDismissed(true)} data-testid="client-2fa-later">
            Maybe later
          </Button>
          <Button onClick={enable} disabled={enabling || code.length < 6 || !setupData}
            data-testid="client-2fa-enable">
            {enabling ? "Verifying…" : "Turn on 2FA"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
