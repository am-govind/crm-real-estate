import { Navigate, Route, Routes } from "react-router-dom";

import { Layout } from "./components/Layout";
import { useMe } from "./lib/auth";
import { AdminPage } from "./pages/admin/AdminPage";
import { DashboardPage } from "./pages/DashboardPage";
import { DocumentRedirectPage } from "./pages/DocumentRedirectPage";
import { DealControlCenterPage } from "./pages/deals/DealControlCenterPage";
import { DealsPage } from "./pages/deals/DealsPage";
import { InventoryPage } from "./pages/inventory/InventoryPage";
import { SiteDetailPage } from "./pages/inventory/SiteDetailPage";
import { MapPage } from "./pages/MapPage";
import { NotificationsPage } from "./pages/NotificationsPage";
import { OwnersPage } from "./pages/OwnersPage";
import { PropertiesPage } from "./pages/properties/PropertiesPage";
import { PropertyDetailPage } from "./pages/properties/PropertyDetailPage";
import { SiteVisitsPage } from "./pages/SiteVisitsPage";
import { TasksPage } from "./pages/TasksPage";
import { NoTenantPage } from "./pages/NoTenantPage";

export function App() {
  const me = useMe();
  if (!me.tenant_id) return <NoTenantPage />;
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<DashboardPage />} />
        <Route path="properties" element={<PropertiesPage />} />
        <Route path="properties/:id" element={<PropertyDetailPage />} />
        <Route path="owners" element={<OwnersPage />} />
        <Route path="deals" element={<DealsPage />} />
        <Route path="deals/:id" element={<DealControlCenterPage />} />
        <Route path="map" element={<MapPage />} />
        <Route path="inventory" element={<InventoryPage />} />
        <Route path="inventory/:id" element={<SiteDetailPage />} />
        <Route path="site-visits" element={<SiteVisitsPage />} />
        <Route path="tasks" element={<TasksPage />} />
        <Route path="notifications" element={<NotificationsPage />} />
        <Route path="documents/:id" element={<DocumentRedirectPage />} />
        <Route path="admin/*" element={<AdminPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
