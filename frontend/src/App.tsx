import { Navigate, Route, Routes } from "react-router-dom";
import { useAuth } from "./auth/AuthContext";
import { Layout } from "./components/Layout";
import Login from "./pages/Login";
import Dashboard from "./pages/student/Dashboard";
import DriveDetail from "./pages/student/DriveDetail";
import Applications from "./pages/student/Applications";
import Profile from "./pages/student/Profile";
import Resumes from "./pages/student/Resumes";
import Notifications from "./pages/student/Notifications";
import AdminDashboard from "./pages/admin/Dashboard";
import AdminDrives from "./pages/admin/Drives";
import AdminDriveDetail from "./pages/admin/DriveDetail";
import AdminApplications from "./pages/admin/Applications";
import AdminStudents from "./pages/admin/Students";
import AdminCompanies from "./pages/admin/Companies";
import AdminAudit from "./pages/admin/AuditLog";

function RequireAuth({ children }: { children: React.ReactNode }) {
  const { user } = useAuth();
  if (!user) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

function RequireAdmin({ children }: { children: React.ReactNode }) {
  const { isAdmin } = useAuth();
  if (!isAdmin) return <Navigate to="/app" replace />;
  return <>{children}</>;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route
        path="/app"
        element={
          <RequireAuth>
            <Layout />
          </RequireAuth>
        }
      >
        <Route index element={<Dashboard />} />
        <Route path="drives/:driveId" element={<DriveDetail />} />
        <Route path="applications" element={<Applications />} />
        <Route path="resumes" element={<Resumes />} />
        <Route path="profile" element={<Profile />} />
        <Route path="notifications" element={<Notifications />} />
        <Route
          path="admin/drives"
          element={
            <RequireAdmin>
              <AdminDrives />
            </RequireAdmin>
          }
        />
        <Route
          path="admin/drives/:driveId"
          element={
            <RequireAdmin>
              <AdminDriveDetail />
            </RequireAdmin>
          }
        />
        <Route
          path="admin/applications"
          element={
            <RequireAdmin>
              <AdminApplications />
            </RequireAdmin>
          }
        />
        <Route
          path="admin/students"
          element={
            <RequireAdmin>
              <AdminStudents />
            </RequireAdmin>
          }
        />
        <Route
          path="admin/companies"
          element={
            <RequireAdmin>
              <AdminCompanies />
            </RequireAdmin>
          }
        />
        <Route
          path="admin/audit"
          element={
            <RequireAdmin>
              <AdminAudit />
            </RequireAdmin>
          }
        />
        <Route
          path="admin"
          element={
            <RequireAdmin>
              <AdminDashboard />
            </RequireAdmin>
          }
        />
      </Route>
      <Route path="*" element={<Navigate to="/app" replace />} />
    </Routes>
  );
}