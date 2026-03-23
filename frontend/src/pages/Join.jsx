import React, { useEffect, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useAuth } from "@/context/AuthContext";
import { api } from "@/lib/api";
import { toast } from "@/components/ui/sonner";

export default function Join() {
  const { user, register, refresh } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [form, setForm] = useState({ email: "", handle: "", password: "" });
  const [invite, setInvite] = useState("");
  const [paymentStatus, setPaymentStatus] = useState("");

  useEffect(() => {
    if (user?.membership_status === "active") {
      navigate("/app");
    }
  }, [user, navigate]);

  useEffect(() => {
    const params = new URLSearchParams(location.search);
    const sessionId = params.get("session_id");
    const canceled = params.get("canceled");
    if (canceled) {
      setPaymentStatus("Payment canceled. Please try again.");
    }
    if (sessionId) {
      checkPaymentStatus(sessionId);
    }
  }, [location.search]);

  const handleRegister = async () => {
    try {
      await register(form.email, form.handle, form.password);
    } catch (error) {
      toast.error("Registration failed.");
    }
  };

  const claimInvite = async () => {
    try {
      await api.post("/auth/invite/claim", { code: invite });
      await refresh();
      toast.success("Membership activated.");
      navigate("/app");
    } catch (error) {
      toast.error("Invite claim failed.");
    }
  };

  const startCheckout = async () => {
    try {
      setPaymentStatus("Redirecting to Stripe checkout...");
      const response = await api.post("/payments/stripe/checkout", {
        origin_url: window.location.origin,
      });
      window.location.href = response.data.url;
    } catch (error) {
      toast.error("Unable to start checkout.");
      setPaymentStatus("Unable to start checkout.");
    }
  };

  const checkPaymentStatus = async (sessionId) => {
    try {
      setPaymentStatus("Checking payment status...");
      const response = await api.get(`/payments/stripe/checkout/status/${sessionId}`);
      if (response.data.payment_status === "paid") {
        setPaymentStatus("Payment confirmed. Membership activated.");
        await refresh();
        navigate("/app");
        return;
      }
      if (response.data.status === "expired") {
        setPaymentStatus("Payment session expired. Try again.");
        return;
      }
      setPaymentStatus("Payment is processing. Refresh in a moment.");
    } catch (error) {
      setPaymentStatus("Unable to verify payment status.");
    }
  };

  return (
    <div className="min-h-screen bg-[#050505] px-6 py-20 text-zinc-100">
      <div className="mx-auto max-w-2xl space-y-8">
        <div>
          <div className="text-xs font-mono uppercase tracking-[0.3em] text-amber-400">
            Join the Pit
          </div>
          <h1 className="mt-3 text-3xl font-semibold uppercase" data-testid="join-title">
            Forge your access
          </h1>
          <p className="mt-2 text-sm text-zinc-400" data-testid="join-subtitle">
            Stage 1.2 supports paid onboarding or invite activation. Register first,
            then activate your membership.
          </p>
        </div>

        {!user && (
          <div
            className="rounded-none border border-zinc-800 bg-zinc-900/60 p-6"
            data-testid="register-card"
          >
            <div className="text-sm font-semibold">Create account</div>
            <div className="mt-4 space-y-3">
              <Input
                placeholder="Email"
                type="email"
                value={form.email}
                onChange={(event) =>
                  setForm((prev) => ({ ...prev, email: event.target.value }))
                }
                className="rounded-none border-zinc-800 bg-zinc-950"
                data-testid="register-email-input"
              />
              <Input
                placeholder="Handle"
                value={form.handle}
                onChange={(event) =>
                  setForm((prev) => ({ ...prev, handle: event.target.value }))
                }
                className="rounded-none border-zinc-800 bg-zinc-950 font-mono"
                data-testid="register-handle-input"
              />
              <Input
                placeholder="Password"
                type="password"
                value={form.password}
                onChange={(event) =>
                  setForm((prev) => ({ ...prev, password: event.target.value }))
                }
                className="rounded-none border-zinc-800 bg-zinc-950"
                data-testid="register-password-input"
              />
              <Button
                onClick={handleRegister}
                className="w-full rounded-none bg-amber-500 font-bold text-black hover:bg-amber-400"
                data-testid="register-submit"
              >
                Register
              </Button>
            </div>
          </div>
        )}

        {user && user.membership_status !== "active" && (
          <div
            className="rounded-none border border-zinc-800 bg-zinc-900/60 p-6"
            data-testid="invite-claim-card"
          >
            <div className="text-sm font-semibold">Activate membership</div>
            <div className="mt-3 rounded-none border border-amber-500/30 bg-amber-500/10 p-4">
              <div className="text-xs font-mono uppercase tracking-[0.2em] text-amber-300">
                Founding Member Join Fee
              </div>
              <div className="mt-2 text-2xl font-semibold" data-testid="join-fee-amount">
                $49 USD
              </div>
              <p className="mt-2 text-xs text-zinc-400">
                Pay once to activate your membership immediately.
              </p>
              <Button
                onClick={startCheckout}
                className="mt-4 w-full rounded-none bg-amber-500 font-bold text-black hover:bg-amber-400"
                data-testid="start-checkout-button"
              >
                Pay join fee
              </Button>
              {paymentStatus && (
                <div className="mt-3 text-xs text-zinc-400" data-testid="payment-status">
                  {paymentStatus}
                </div>
              )}
            </div>
            <div className="mt-4 space-y-3">
              <Input
                placeholder="Invite code"
                value={invite}
                onChange={(event) => setInvite(event.target.value)}
                className="rounded-none border-zinc-800 bg-zinc-950 font-mono"
                data-testid="invite-code-input"
              />
              <Button
                onClick={claimInvite}
                className="w-full rounded-none bg-cyan-500 text-black hover:bg-cyan-400"
                data-testid="invite-claim-submit"
              >
                Claim invite
              </Button>
            </div>
          </div>
        )}

        <div className="text-sm text-zinc-500" data-testid="join-login-link">
          Already inside?{" "}
          <Link
            to="/login"
            className="text-amber-400"
            data-testid="join-login-anchor"
          >
            Log in
          </Link>
        </div>
      </div>
    </div>
  );
}
