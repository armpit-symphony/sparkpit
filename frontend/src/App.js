import "@/App.css";
import { BrowserRouter, Routes, Route, Navigate, useLocation } from "react-router-dom";
import { ThemeProvider } from "next-themes";
import { AuthProvider, useAuth } from "@/context/AuthContext";
import { AppShell } from "@/components/layout/AppShell";
import Landing from "@/pages/Landing";
import BotInvite from "@/pages/BotInvite";
import Join from "@/pages/Join";
import Login from "@/pages/Login";
import Lobby from "@/pages/Lobby";
import Research from "@/pages/Research";
import Rooms from "@/pages/Rooms";
import Bounties from "@/pages/Bounties";
import BountyDetail from "@/pages/BountyDetail";
import Bots from "@/pages/Bots";
import Settings from "@/pages/Settings";
import Activity from "@/pages/Activity";
import OpsChecklist from "@/pages/OpsChecklist";
import Moderation from "@/pages/Moderation";
import { Toaster } from "@/components/ui/sonner";
import {
  buildLoginPath,
  getCurrentPathWithSearch,
} from "@/lib/authRouting";
import { canPostConversations } from "@/lib/access";

const LoadingScreen = () => (
  <div
    className="flex min-h-screen items-center justify-center bg-[#050505] text-zinc-400"
    data-testid="loading-screen"
  >
    Loading...
  </div>
);

const RequireRegistered = ({ children }) => {
  const { user, loading } = useAuth();
  const location = useLocation();
  if (loading) return <LoadingScreen />;
  if (!user) {
    return <Navigate to={buildLoginPath(getCurrentPathWithSearch(location))} replace />;
  }
  return children;
};

const RequireAdmin = ({ children }) => {
  const { user, loading } = useAuth();
  const location = useLocation();
  if (loading) return <LoadingScreen />;
  if (!user) {
    return <Navigate to={buildLoginPath(getCurrentPathWithSearch(location))} replace />;
  }
  if (user.role !== "admin") {
    return <Navigate to="/app/lobby" replace />;
  }
  return children;
};

const AppIndexRedirect = () => {
  const { user, loading } = useAuth();
  if (loading) return <LoadingScreen />;
  if (!user) return <Navigate to={buildLoginPath("/app")} replace />;
  return <Navigate to={canPostConversations(user) ? "/app/lobby" : "/app/research"} replace />;
};

function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<Landing />} />
      <Route path="/bot" element={<BotInvite />} />
      <Route path="/bot-invite" element={<BotInvite />} />
      <Route path="/join" element={<Join />} />
      <Route path="/login" element={<Login />} />
      <Route
        path="/app"
        element={
          <RequireRegistered>
            <AppShell />
          </RequireRegistered>
        }
      >
        <Route index element={<AppIndexRedirect />} />
        <Route path="lobby" element={<Lobby />} />
        <Route path="research" element={<Research />} />
        <Route path="rooms" element={<Rooms />} />
        <Route path="rooms/:slug" element={<Rooms />} />
        <Route path="rooms/:slug/:channelId" element={<Rooms />} />
        <Route path="bounties" element={<Bounties />} />
        <Route path="bounties/:id" element={<BountyDetail />} />
        <Route path="bots" element={<Bots />} />
        <Route path="activity" element={<Activity />} />
        <Route
          path="ops"
          element={
            <RequireAdmin>
              <OpsChecklist />
            </RequireAdmin>
          }
        />
        <Route
          path="moderation"
          element={
            <RequireAdmin>
              <Moderation />
            </RequireAdmin>
          }
        />
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
