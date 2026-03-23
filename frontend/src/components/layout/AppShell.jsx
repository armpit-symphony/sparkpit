import React, { createContext, useContext, useEffect, useState } from "react";
import { Outlet, useLocation } from "react-router-dom";
import { api } from "@/lib/api";
import { RoomsSidebar } from "@/components/layout/RoomsSidebar";
import { QuickPanel } from "@/components/layout/QuickPanel";
import { toast } from "@/components/ui/sonner";

const AppDataContext = createContext(null);
const LayoutContext = createContext(null);

export const useAppData = () => useContext(AppDataContext);
export const useLayout = () => useContext(LayoutContext);

export const AppShell = () => {
  const [rooms, setRooms] = useState([]);
  const [loadingRooms, setLoadingRooms] = useState(true);
  const [secondaryPanel, setSecondaryPanel] = useState(<QuickPanel />);
  const location = useLocation();

  const fetchRooms = async () => {
    try {
      setLoadingRooms(true);
      const response = await api.get("/rooms");
      setRooms(response.data.items || []);
    } catch (error) {
      toast.error("Unable to load rooms.");
    } finally {
      setLoadingRooms(false);
    }
  };

  useEffect(() => {
    fetchRooms();
  }, []);

  useEffect(() => {
    setSecondaryPanel(<QuickPanel />);
  }, [location.pathname]);

  return (
    <AppDataContext.Provider value={{ rooms, refreshRooms: fetchRooms, loadingRooms }}>
      <LayoutContext.Provider value={{ setSecondaryPanel }}>
        <div
          className="min-h-screen bg-[#050505] text-zinc-100"
          data-testid="app-shell"
        >
          <div className="flex h-screen overflow-hidden">
            <RoomsSidebar />
            <aside
              className="hidden h-full w-64 shrink-0 border-r border-zinc-800 bg-zinc-950/70 lg:block"
              data-testid="app-secondary-panel"
            >
              {secondaryPanel}
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
