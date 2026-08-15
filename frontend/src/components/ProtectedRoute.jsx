import { Navigate, useLocation } from "react-router-dom";
import { useAuth } from "@/contexts/AuthContext";
import { Loader2 } from "lucide-react";

export default function ProtectedRoute({ children, roles }) {
  const { user } = useAuth();
  const location = useLocation();

  if (user === null) {
    return (
      <div className="flex h-screen w-full items-center justify-center bg-background" data-testid="auth-loading">
        <Loader2 className="h-6 w-6 animate-spin text-graphite" />
      </div>
    );
  }

  if (user === false) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  if (roles && !roles.includes(user.role)) {
    // Each role has exactly one home. A founding member is not a client and
    // must not be bounced into the client portal.
    const home = { client: "/portal", founding: "/founding-portal" }[user.role] || "/dashboard";
    return <Navigate to={home} replace />;
  }

  return children;
}
