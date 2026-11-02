import React, { useEffect } from 'react';
import { Routes, Route, Navigate, useLocation } from 'react-router-dom';
import { useAuth } from './context/AuthContext';
import { PageLoader } from './components/ui';
import DesktopOnly from './components/DesktopOnly';
import NoAccess from './components/NoAccess';
import OfflineBanner from './components/OfflineBanner';
import { ToastProvider } from './components/Toaster';
import { LANGUAGES, useI18n } from './i18n';
import { setTimeZone } from './utils';
import LoginPage from './pages/LoginPage';
import SignupPage from './pages/SignupPage';
import OrgSignupPage from './pages/OrgSignupPage';
import ForgotPasswordPage from './pages/ForgotPasswordPage';
import ResetPasswordPage from './pages/ResetPasswordPage';
import VerifyEmailPage from './pages/VerifyEmailPage';
import WaitlistPage from './pages/WaitlistPage';
import WaitlistUnsubscribePage from './pages/WaitlistUnsubscribePage';
import OrganizationsPage from './pages/OrganizationsPage';
import AdminQuestionsPage from './pages/AdminQuestionsPage';
import QuestionEditorPage from './pages/QuestionEditorPage';
import AdminExamsPage from './pages/AdminExamsPage';
import ExamFormPage from './pages/ExamFormPage';
import ExamResultsPage from './pages/ExamResultsPage';
import ResultCardsPage from './pages/ResultCardsPage';
import IntegrityReportPage from './pages/IntegrityReportPage';
import AdminStudentsPage from './pages/AdminStudentsPage';
import AdminOrganizationPage from './pages/AdminOrganizationPage';
import AdminEvaluateAnswersPage from './pages/AdminEvaluateAnswersPage';
import GradeByQuestionPage from './pages/GradeByQuestionPage';
import ExamAnalysisPage from './pages/ExamAnalysisPage';
import StudentDashboard from './pages/StudentDashboard';
import ExamPage from './pages/ExamPage';
import StudentExamsPage from './pages/StudentExamsPage';
import StudentResultsPage from './pages/StudentResultsPage';
import StudentProfilePage from './pages/StudentProfilePage';

function App() {
  const { user, isLoading, currentMembership, isStaff, isManager, isCandidate } = useAuth();
  const { language, setLanguage } = useI18n();
  const location = useLocation();

  // Set during render so every date on this render already uses the organization's timezone
  setTimeZone(currentMembership?.timezone);

  // The account's language wins, then the organization's. ?lang= in the URL overrides both, and a
  // test pseudo-language (en-XA, en-XB) stays until it's changed, so it survives reloads
  const preferredLanguage = user?.language || currentMembership?.default_language;
  useEffect(() => {
    const testing = !LANGUAGES.some((l) => l.code === language);
    if (preferredLanguage && !testing && !new URLSearchParams(window.location.search).has('lang')) setLanguage(preferredLanguage);
  }, [preferredLanguage, setLanguage]); // eslint-disable-line react-hooks/exhaustive-deps -- only when the preference changes

  if (isLoading) {
    return <div className="min-h-screen bg-paper"><PageLoader /></div>;
  }

  // Pages for one kind of member. Signed out: to sign in, then back here. Signed in without an organization:
  // pick one. Otherwise say why the page isn't theirs (NoAccess) instead of quietly sending them elsewhere.
  const only = (allowed, element, need) => {
    if (allowed) return element;
    if (!user) return <Navigate to="/login" replace state={{ from: `${location.pathname}${location.search}` }} />;
    if (!currentMembership) return <Navigate to="/organizations" replace />;
    return <NoAccess need={need} />;
  };

  return (
    <ToastProvider>
    {/* The exam page shows its own connection status, next to its answers */}
    {!location.pathname.startsWith('/exam/') && <OfflineBanner />}
    <DesktopOnly>
    <Routes>
      <Route
        path="/"
        element={
          !user ? <Navigate to="/login" replace />
            : !currentMembership ? <Navigate to="/organizations" replace />
              : isStaff ? <Navigate to="/admin-exams" replace />
                : <Navigate to="/student-account" replace />
        }
      />
      <Route path="/login" element={user ? <Navigate to="/" replace /> : <LoginPage />} />
      <Route path="/signup" element={user ? <Navigate to="/" replace /> : <SignupPage />} />
      <Route path="/signup/organization" element={<OrgSignupPage />} />
      <Route path="/forgot-password" element={user ? <Navigate to="/" replace /> : <ForgotPasswordPage />} />
      <Route path="/reset-password/:token" element={<ResetPasswordPage />} />
      <Route path="/invite/:token" element={<ResetPasswordPage invite />} />
      <Route path="/verify-email/:token" element={<VerifyEmailPage />} />
      <Route path="/waitlist" element={<WaitlistPage />} />
      <Route path="/waitlist/unsubscribe/:token" element={<WaitlistUnsubscribePage />} />
      <Route path="/organizations" element={user ? <OrganizationsPage /> : <Navigate to="/login" replace />} />
      <Route path="/profile" element={only(currentMembership, <StudentProfilePage />, 'member')} />

      {/* Staff */}
      <Route path="/admin-exams" element={only(isStaff, <AdminExamsPage />, 'staff')} />
      <Route path="/admin-exams/new" element={only(isStaff, <ExamFormPage />, 'staff')} />
      <Route path="/admin-exams/:examId/edit" element={only(isStaff, <ExamFormPage />, 'staff')} />
      <Route path="/admin-exams/:examId" element={only(isStaff, <ExamResultsPage />, 'staff')} />
      <Route path="/admin-exams/:examId/cards" element={only(isStaff, <ResultCardsPage />, 'staff')} />
      <Route path="/admin-exams/:examId/grade" element={only(isStaff, <GradeByQuestionPage />, 'staff')} />
      <Route path="/admin-exams/:examId/analysis" element={only(isStaff, <ExamAnalysisPage />, 'staff')} />
      <Route path="/admin-exams/:examId/grade/:questionId" element={only(isStaff, <GradeByQuestionPage />, 'staff')} />
      <Route path="/admin-integrity/:attemptId" element={only(isStaff, <IntegrityReportPage />, 'staff')} />
      <Route path="/admin-evaluate-answers/:attemptId" element={only(isStaff, <AdminEvaluateAnswersPage />, 'staff')} />
      <Route path="/admin-questions" element={only(isStaff, <AdminQuestionsPage />, 'staff')} />
      <Route path="/admin-questions/new" element={only(isStaff, <QuestionEditorPage />, 'staff')} />
      <Route path="/admin-questions/:questionId/edit" element={only(isStaff, <QuestionEditorPage />, 'staff')} />
      <Route path="/admin-students" element={only(isStaff, <AdminStudentsPage />, 'staff')} />
      <Route path="/admin-organization" element={only(isManager, <AdminOrganizationPage />, 'manager')} />

      {/* Students */}
      <Route path="/student-account" element={only(isCandidate, <StudentDashboard />, 'candidate')} />
      <Route path="/exam/:id" element={only(isCandidate, <ExamPage />, 'candidate')} />
      <Route path="/exam/resume/:attemptId" element={only(isCandidate, <ExamPage />, 'candidate')} />
      <Route path="/student-exams" element={only(isCandidate, <StudentExamsPage />, 'candidate')} />
      <Route path="/exam-results/:attemptId" element={only(isCandidate, <StudentResultsPage />, 'candidate')} />
      <Route path="/student-profile" element={<Navigate to="/profile" replace />} />

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
    </DesktopOnly>
    </ToastProvider>
  );
}

export default App;
