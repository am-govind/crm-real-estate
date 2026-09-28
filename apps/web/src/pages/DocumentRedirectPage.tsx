import { useQuery } from "@tanstack/react-query";
import { Navigate, useParams } from "react-router-dom";

import { api } from "../lib/api";

/** Notification links point at /documents/:id; send the user to the document's deal or property. */
export function DocumentRedirectPage() {
  const { id = "" } = useParams();
  const doc = useQuery({ queryKey: ["documents", "detail", id], queryFn: () => api.documents.get(id) });
  if (doc.isLoading) return <div className="muted">Loading…</div>;
  const d = doc.data;
  if (d?.deal_id) return <Navigate to={`/deals/${d.deal_id}?tab=documents`} replace />;
  if (d?.property_id) return <Navigate to={`/properties/${d.property_id}?tab=documents`} replace />;
  return <div className="muted">Document not available.</div>;
}
