import { Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider, useAuth } from './hooks/useAuth';
import { AppLayout } from './components/layout/AppLayout';
import { LoginPage } from './pages/LoginPage';
import { DashboardPage } from './pages/DashboardPage';
import { WorkbenchPage } from './pages/WorkbenchPage';
import { InboxPage } from './pages/InboxPage';
import { ReportFormPage } from './pages/ReportFormPage';
import { LiteratureSweepPage } from './pages/LiteratureSweepPage';

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { isAuthenticated, isLoading } = useAuth();

  if (isLoading) {
    return (
      <div className="flex h-screen items-center justify-center">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary-200 border-t-primary-600" />
      </div>
    );
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  return <>{children}</>;
}

export default function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route
          path="/*"
          element={
            <ProtectedRoute>
              <AppLayout>
                <Routes>
                  <Route path="/" element={<DashboardPage />} />
                  <Route path="/report" element={<ReportFormPage />} />
                  <Route path="/literature" element={<LiteratureSweepPage />} />
                  <Route path="/inbox" element={<InboxPage />} />
                  <Route path="/cases/:caseId" element={<WorkbenchPage />} />
                </Routes>
              </AppLayout>
            </ProtectedRoute>
          }
        />
      </Routes>
    </AuthProvider>
  );
}
