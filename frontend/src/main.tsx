import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import Layout from "./components/Layout";
import { Loading } from "./components/ui";
import "./index.css";
import { AppProvider, ToastProvider, useApp } from "./lib/app";
import Conflicts, { ConflictDetail } from "./pages/Conflicts";
import Dashboard from "./pages/Dashboard";
import { Actions, Approvals, Reminders } from "./pages/Execution";
import Login from "./pages/Login";
import MeetingDetail from "./pages/MeetingDetail";
import Meetings from "./pages/Meetings";
import Memory from "./pages/Memory";
import NewMeeting from "./pages/NewMeeting";
import { Audit, Digest, IntegrationsPage, Projects } from "./pages/Workspace";

function Root() {
  const { user, booting } = useApp();
  if (booting) return <Loading label="Starting" />;
  if (!user) return <Login />;
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Dashboard />} />
        <Route path="projects" element={<Projects />} />
        <Route path="meetings" element={<Meetings />} />
        <Route path="meetings/new" element={<NewMeeting />} />
        <Route path="meetings/:id" element={<MeetingDetail />} />
        <Route path="memory" element={<Memory />} />
        <Route path="conflicts" element={<Conflicts />} />
        <Route path="conflicts/:id" element={<ConflictDetail />} />
        <Route path="approvals" element={<Approvals />} />
        <Route path="actions" element={<Actions />} />
        <Route path="reminders" element={<Reminders />} />
        <Route path="digest" element={<Digest />} />
        <Route path="integrations" element={<IntegrationsPage />} />
        <Route path="audit" element={<Audit />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter>
      <ToastProvider>
        <AppProvider>
          <Root />
        </AppProvider>
      </ToastProvider>
    </BrowserRouter>
  </React.StrictMode>,
);
