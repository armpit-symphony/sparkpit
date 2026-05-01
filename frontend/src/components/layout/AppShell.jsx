import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { Outlet, useLocation } from "react-router-dom";
import { api } from "@/lib/api";
import { RoomsSidebar } from "@/components/layout/RoomsSidebar";
import { QuickPanel } from "@/components/layout/QuickPanel";
import { WelcomeModal } from "@/components/onboarding/WelcomeModal";
import { toast } from "@/components/ui/sonner";
import { useAuth } from "@/context/AuthContext";

const AppDataContext = createContext(null);
const LayoutContext = createContext(null);

const DEFAULT_SECONDARY_PANEL_LAYOUT = {
  railKey: "quick-panel",
  expandedWidthClass: "w-64",
  collapsedWidthClass: "w-16",
  collapsible: true,
  defaultCollapsed: false,
  collapsed: false,
  hidden: false,
};

const getRailStorageKey = (userId, railKey) =>
  `sparkpit:secondary-rail:v1:${userId || "anon"}:${railKey}`;

const readStoredRailState = (userId, railKey, fallback) => {
  if (!railKey || typeof window === "undefined") return fallback;
  try {
    const value = window.localStorage.getItem(getRailStorageKey(userId, railKey));
    if (value === "collapsed") return true;
    if (value === "expanded") return false;
  } catch (error) {
    return fallback;
  }
  return fallback;
};

const writeStoredRailState = (userId, railKey, collapsed) => {
  if (!railKey || typeof window === "undefined") return;
  try {
    window.localStorage.setItem(
      getRailStorageKey(userId, railKey),
      collapsed ? "collapsed" : "expanded",
    );
  } catch (error) {
    // no-op: persistence is best effort only
  }
};

export const useAppData = () => useContext(AppDataContext);
export const useLayout = () => useContext(LayoutContext);

export const AppShell = () => {
  const { user } = useAuth();
  const [rooms, setRooms] = useState([]);
  const [loadingRooms, setLoadingRooms] = useState(true);
  const [secondaryPanel, setSecondaryPanel] = useState(<QuickPanel />);
  const [secondaryPanelLayout, setSecondaryPanelLayout] = useState(DEFAULT_SECONDARY_PANEL_LAYOUT);
  const location = useLocation();

  const fetchRooms = useCallback(async () => {
    try {
      setLoadingRooms(true);
      const response = await api.get("/rooms");
      setRooms(response.data.items || []);
    } catch (error) {
      toast.error("Unable to load rooms.");
    } finally {
      setLoadingRooms(false);
    }
  }, []);

  useEffect(() => {
    fetchRooms();
  }, [fetchRooms]);

  const configureSecondaryPanel = useCallback(
    (nextLayout = {}) => {
      setSecondaryPanelLayout((current) => {
        const merged = {
          ...DEFAULT_SECONDARY_PANEL_LAYOUT,
          ...current,
          ...nextLayout,
        };

        if (merged.hidden || !merged.collapsible) {
          return {
            ...merged,
            collapsed: false,
          };
        }

        const hasExplicitCollapsed = typeof nextLayout.collapsed === "boolean";
        const collapsed = hasExplicitCollapsed
          ? nextLayout.collapsed
          : readStoredRailState(user?.id, merged.railKey, merged.defaultCollapsed);

        return {
          ...merged,
          collapsed,
        };
      });
    },
    [user?.id],
  );

  const toggleSecondaryPanelCollapsed = useCallback(() => {
    setSecondaryPanelLayout((current) => {
      if (current.hidden || !current.collapsible) {
        return current;
      }
      const nextCollapsed = !current.collapsed;
      writeStoredRailState(user?.id, current.railKey, nextCollapsed);
      return {
        ...current,
        collapsed: nextCollapsed,
      };
    });
  }, [user?.id]);

  const setSecondaryPanelWidth = useCallback(
    (widthClass) => {
      configureSecondaryPanel({ expandedWidthClass: widthClass });
    },
    [configureSecondaryPanel],
  );

  useEffect(() => {
    setSecondaryPanel(<QuickPanel />);
    configureSecondaryPanel({
      railKey: "quick-panel",
      expandedWidthClass: "w-64",
      collapsedWidthClass: "w-16",
      collapsible: true,
      defaultCollapsed: false,
      hidden: false,
    });
  }, [configureSecondaryPanel, location.pathname]);

  const renderedSecondaryPanel = useMemo(() => {
    if (!secondaryPanel || secondaryPanelLayout.hidden) {
      return null;
    }
    if (React.isValidElement(secondaryPanel)) {
      return React.cloneElement(secondaryPanel, {
        collapsed: secondaryPanelLayout.collapsed,
        onToggleCollapsed: toggleSecondaryPanelCollapsed,
      });
    }
    return secondaryPanel;
  }, [
    secondaryPanel,
    secondaryPanelLayout.collapsed,
    secondaryPanelLayout.hidden,
    toggleSecondaryPanelCollapsed,
  ]);

  const secondaryPanelWidthClass = secondaryPanelLayout.hidden
    ? "w-0 border-r-0"
    : secondaryPanelLayout.collapsed
      ? secondaryPanelLayout.collapsedWidthClass
      : secondaryPanelLayout.expandedWidthClass;

  return (
    <AppDataContext.Provider value={{ rooms, refreshRooms: fetchRooms, loadingRooms }}>
      <LayoutContext.Provider
        value={{
          setSecondaryPanel,
          setSecondaryPanelWidth,
          configureSecondaryPanel,
          secondaryPanelCollapsed: secondaryPanelLayout.collapsed,
          toggleSecondaryPanelCollapsed,
        }}
      >
        <div
          className="min-h-screen bg-[#050505] text-zinc-100"
          data-testid="app-shell"
        >
          <WelcomeModal user={user} />
          <div className="flex h-screen overflow-hidden">
            <RoomsSidebar />
            <aside
              className={`hidden h-full shrink-0 border-r border-zinc-800 bg-zinc-950/70 transition-[width] duration-200 lg:block ${secondaryPanelWidthClass}`}
              data-testid="app-secondary-panel"
            >
              {renderedSecondaryPanel}
            </aside>
            <main className="flex-1 min-w-0 overflow-hidden" data-testid="app-main">
              <Outlet />
            </main>
          </div>
        </div>
      </LayoutContext.Provider>
    </AppDataContext.Provider>
  );
};
