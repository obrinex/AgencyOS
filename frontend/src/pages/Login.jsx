import { useState } from "react";
import { Navigate } from "react-router-dom";
import { motion } from "framer-motion";
import { useAuth } from "@/contexts/AuthContext";
import { formatApiError } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { InputOTP, InputOTPGroup, InputOTPSlot } from "@/components/ui/input-otp";
import { Loader2, ShieldCheck } from "lucide-react";
import { toast } from "sonner";

export default function Login() {
  const { login, verify2FA, user } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [requires2FA, setRequires2FA] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  if (user && user !== false) {
    return <Navigate to={user.role === "client" ? "/portal" : "/dashboard"} replace />;
  }

  const handleLogin = async (e) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const result = await login(email, password);
      if (result.requires2FA) {
        setRequires2FA(true);
      } else {
        toast.success("Welcome back!");
      }
    } catch (err) {
      setError(formatApiError(err.response?.data?.detail));
    } finally {
      setLoading(false);
    }
  };

  const handleVerify2FA = async (e) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await verify2FA(code);
      toast.success("Welcome back!");
    } catch (err) {
      setError(formatApiError(err.response?.data?.detail));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex min-h-screen w-full items-center justify-center bg-background px-4" data-testid="login-page">
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        <div className="absolute -top-40 -left-40 h-96 w-96 rounded-full bg-white/[0.03] blur-3xl" />
        <div className="absolute -bottom-40 -right-40 h-96 w-96 rounded-full bg-white/[0.03] blur-3xl" />
      </div>

      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4 }}
        className="relative w-full max-w-sm"
      >
        <div className="flex flex-col items-center mb-8">
          <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-foreground text-background font-display font-bold text-lg mb-4">O</div>
          <h1 className="font-display text-xl font-bold tracking-tight">AgencyOS</h1>
          <p className="font-mono text-[11px] text-graphite tracking-widest mt-0.5">BY OBRINEX</p>
        </div>

        <div className="rounded-2xl border border-white/10 bg-surface-1 p-6">
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
              <div className="flex flex-col items-center gap-2 mb-2">
                <ShieldCheck className="h-6 w-6 text-info" />
                <p className="text-sm text-ash text-center">Enter the 6-digit code from your authenticator app</p>
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
              {error && <p data-testid="twofa-error" className="text-sm text-danger text-center">{error}</p>}
              <Button data-testid="twofa-submit-button" type="submit" disabled={loading || code.length < 6} className="w-full">
                {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : "Verify"}
              </Button>
            </form>
          )}
        </div>
        <p className="mt-6 text-center font-mono text-[11px] text-carbon">AGENCY OPERATING SYSTEM · EST. 2026</p>
      </motion.div>
    </div>
  );
}
