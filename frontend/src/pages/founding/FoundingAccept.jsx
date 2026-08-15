import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { Loader2, CheckCircle2 } from "lucide-react";
import api, { formatApiError } from "@/lib/api";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { toast } from "sonner";

const MIN_LENGTH = 10;

/** Where an approval email lands. The member chooses their own password here
 *  rather than being emailed a working one — a credential mailed in plain text
 *  lives in that inbox forever. The token is single-use. */
export default function FoundingAccept() {
  const { token } = useParams();
  const navigate = useNavigate();
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [saving, setSaving] = useState(false);
  const [done, setDone] = useState(false);

  const tooShort = password.length > 0 && password.length < MIN_LENGTH;
  const mismatch = confirm.length > 0 && password !== confirm;
  const ready = password.length >= MIN_LENGTH && password === confirm;

  const submit = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      await api.post("/public/founding/accept", { token, password });
      setDone(true);
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    } finally { setSaving(false); }
  };

  return (
    <div className="min-h-screen flex items-center justify-center p-6">
      <Card className="w-full max-w-md p-7 bg-surface-1 border-white/10" data-testid="founding-accept-page">
        {done ? (
          <div className="text-center space-y-4">
            <CheckCircle2 className="h-8 w-8 text-success mx-auto" />
            <h1 className="font-display text-xl font-bold">You're set up</h1>
            <p className="text-sm text-graphite">
              Sign in with your email and the password you just chose.
            </p>
            <Button onClick={() => navigate("/login")} data-testid="founding-accept-login">
              Go to sign in
            </Button>
          </div>
        ) : (
          <form onSubmit={submit} className="space-y-4">
            <div>
              <h1 className="font-display text-xl font-bold">Welcome to the Founding Circle</h1>
              <p className="mt-1 text-sm text-graphite">
                Choose a password and your portal is ready.
              </p>
            </div>

            <div className="space-y-1">
              <Label>Password</Label>
              <Input
                type="password" value={password} autoComplete="new-password"
                onChange={(e) => setPassword(e.target.value)}
                className="bg-surface-2 border-white/10"
                data-testid="founding-accept-password"
              />
              <p className={`text-xs ${tooShort ? "text-danger" : "text-carbon"}`}>
                At least {MIN_LENGTH} characters.
              </p>
            </div>

            <div className="space-y-1">
              <Label>Confirm password</Label>
              <Input
                type="password" value={confirm} autoComplete="new-password"
                onChange={(e) => setConfirm(e.target.value)}
                className="bg-surface-2 border-white/10"
                data-testid="founding-accept-confirm"
              />
              {mismatch && <p className="text-xs text-danger">These don't match.</p>}
            </div>

            <Button type="submit" disabled={!ready || saving} className="w-full gap-1.5"
                    data-testid="founding-accept-submit">
              {saving && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
              Create my account
            </Button>

            <p className="text-xs text-carbon text-center">
              This link works once. Membership isn't announced publicly.
            </p>
          </form>
        )}
      </Card>
    </div>
  );
}
