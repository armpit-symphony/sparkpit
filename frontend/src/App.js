import "@/App.css";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { ThemeProvider } from "next-themes";
import { AuthProvider, useAuth } from "@/context/AuthContext";
import { AppShell } from "@/components/layout/AppShell";
import Landing from "@/pages/Landing";
import Join from "@/pages/Join";
import Login from "@/pages/Login";
import Rooms from "@/pages/Rooms";
import Bounties from "@/pages/Bounties";
import BountyDetail from "@/pages/BountyDetail";
import Bots from "@/pages/Bots";
import Settings from "@/pages/Settings";
import Activity from "@/pages/Activity";
import OpsChecklist from "@/pages/OpsChecklist";
import { Toaster } from "@/components/ui/sonner";

const LoadingScreen = () => (
  <div
    className="flex min-h-screen items-center justify-center bg-[#050505] text-zinc-400"
    data-testid="loading-screen"
  >
    Loading...
  </div>
);

const RequireActive = ({ children }) => {
  const { user, loading } = useAuth();
  if (loading) return <LoadingScreen />;
  if (!user) return <Navigate to="/login" replace />;
  if (user.membership_status !== "active") {
    return <Navigate to="/join" replace />;
  }
  return children;
};

function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<Landing />} />
      <Route path="/join" element={<Join />} />
      <Route path="/login" element={<Login />} />
      <Route
        path="/app"
        element={
          <RequireActive>
            <AppShell />
          </RequireActive>
        }
      >
        <Route index element={<Navigate to="bounties" replace />} />
        <Route path="rooms" element={<Rooms />} />
        <Route path="rooms/:slug" element={<Rooms />} />
        <Route path="rooms/:slug/:channelId" element={<Rooms />} />
        <Route path="bounties" element={<Bounties />} />
        <Route path="bounties/:id" element={<BountyDetail />} />
        <Route path="bots" element={<Bots />} />
        <Route path="activity" element={<Activity />} />
        <Route path="ops" element={<OpsChecklist />} />
        <Route path="settings" element={<Settings />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

function App() {
  return (
    <ThemeProvider attribute="class" defaultTheme="dark" enableSystem={false}>
      <AuthProvider>
        <BrowserRouter>
          <AppRoutes />
        </BrowserRouter>
        <Toaster />
      </AuthProvider>
    </ThemeProvider>
  );
}

export default App;
