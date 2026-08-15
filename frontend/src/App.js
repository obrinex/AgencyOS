import "@/App.css";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { AuthProvider } from "@/contexts/AuthContext";
import { Toaster } from "@/components/ui/sonner";
import { DarkGradientBg } from "@/components/ui/elegant-dark-pattern";
import ProtectedRoute from "@/components/ProtectedRoute";
import AppLayout from "@/components/layout/AppLayout";
import PortalLayout from "@/components/layout/PortalLayout";

import Login from "@/pages/Login";
import FoundingAccept from "@/pages/founding/FoundingAccept";
import FoundingPortal from "@/pages/founding/FoundingPortal";
import FoundingReview from "@/pages/founding/FoundingReview";
import FoundingMembers from "@/pages/founding/FoundingMembers";
import FoundingCommunity from "@/pages/founding/FoundingCommunity";
import Dashboard from "@/pages/Dashboard";
import CRMPipeline from "@/pages/crm/CRMPipeline";
import LeadDetail from "@/pages/crm/LeadDetail";
import Contacts from "@/pages/Contacts";
import Clients from "@/pages/Clients";
import ClientDetail from "@/pages/ClientDetail";
import Projects from "@/pages/Projects";
import ProjectDetail from "@/pages/ProjectDetail";
import Tasks from "@/pages/Tasks";
import Finance from "@/pages/Finance";
import Invoices from "@/pages/Invoices";
import InvoiceDetail from "@/pages/InvoiceDetail";
import Proposals from "@/pages/Proposals";
import ProposalDetail from "@/pages/ProposalDetail";
import Contracts from "@/pages/Contracts";
import Support from "@/pages/Support";
import TicketDetail from "@/pages/TicketDetail";
import KnowledgeBase from "@/pages/KnowledgeBase";
import Vault from "@/pages/Vault";
import Files from "@/pages/Files";
import Automations from "@/pages/Automations";
import Analytics from "@/pages/Analytics";
import Settings from "@/pages/Settings";
import Notes from "@/pages/Notes";
import Help from "@/pages/Help";
import Calendar from "@/pages/Calendar";
import BookMeeting from "@/pages/BookMeeting";
import ManageMeeting from "@/pages/ManageMeeting";
import PublicAgreement from "@/pages/PublicAgreement";
import LeadCapture from "@/pages/LeadCapture";
import PublicProject from "@/pages/PublicProject";
import LeadFinder from "@/pages/LeadFinder";
import PayInvoice from "@/pages/PayInvoice";
import Emails from "@/pages/Emails";
import Chat from "@/pages/Chat";
import Policies from "@/pages/Policies";
import PaymentLinks from "@/pages/PaymentLinks";

import PortalDashboard from "@/pages/portal/PortalDashboard";
import PortalProjects from "@/pages/portal/PortalProjects";
import PortalProjectDetail from "@/pages/portal/PortalProjectDetail";
import PortalInvoices from "@/pages/portal/PortalInvoices";
import PortalContracts from "@/pages/portal/PortalContracts";
import PortalFiles from "@/pages/portal/PortalFiles";
import PortalSupport from "@/pages/portal/PortalSupport";
import PortalChat from "@/pages/portal/PortalChat";
import PortalPolicies from "@/pages/portal/PortalPolicies";
import PortalTicketDetail from "@/pages/portal/PortalTicketDetail";
import PublicProposal from "@/pages/PublicProposal";

function App() {
  return (
    <div className="App">
      {/* The ground, mounted once for the entire product.

          Here rather than in AppLayout because "everywhere" has to include
          the surfaces that have no layout: Login, the public proposal and
          agreement pages, the founding portal, the pay-invoice screen. One
          fixed layer at the root also means it is painted once and never
          re-rendered on navigation — mounting it per page would rebuild
          five masked gradient layers on every route change. */}
      <DarkGradientBg fixed />
      <BrowserRouter>
        <AuthProvider>
          <Routes>
            <Route path="/" element={<Navigate to="/login" replace />} />
            <Route path="/login" element={<Login />} />
            <Route path="/proposal/:token" element={<PublicProposal />} />
            <Route path="/book/:slug" element={<BookMeeting />} />
            <Route path="/meeting/:token" element={<ManageMeeting />} />
            <Route path="/agreement/:token" element={<PublicAgreement />} />
            <Route path="/start/:slug" element={<LeadCapture />} />
            <Route path="/status/:token" element={<PublicProject />} />
            <Route path="/pay/:token" element={<PayInvoice />} />
            <Route path="/founding/accept/:token" element={<FoundingAccept />} />

            {/* The Founding Circle portal is its own tree, outside AppLayout —
                members do not get the staff sidebar or the client portal. */}
            <Route
              path="/founding-portal"
              element={
                <ProtectedRoute roles={["founding"]}>
                  <FoundingPortal />
                </ProtectedRoute>
              }
            />

            <Route
              element={
                <ProtectedRoute roles={["admin", "team_member"]}>
                  <AppLayout />
                </ProtectedRoute>
              }
            >
              <Route path="/dashboard" element={<Dashboard />} />
              <Route path="/crm" element={<CRMPipeline />} />
              <Route path="/founding" element={<FoundingReview />} />
              <Route path="/founding/members" element={<FoundingMembers />} />
              <Route path="/founding/community" element={<FoundingCommunity />} />
              <Route path="/lead-finder" element={<LeadFinder />} />
              <Route path="/crm/:id" element={<LeadDetail />} />
              <Route path="/contacts" element={<Contacts />} />
              <Route path="/clients" element={<Clients />} />
              <Route path="/clients/:id" element={<ClientDetail />} />
              <Route path="/projects" element={<Projects />} />
              <Route path="/projects/:id" element={<ProjectDetail />} />
              <Route path="/tasks" element={<Tasks />} />
              <Route path="/finance" element={<Finance />} />
              <Route path="/invoices" element={<Invoices />} />
              <Route path="/payment-links" element={<PaymentLinks />} />
              <Route path="/emails" element={<Emails />} />
              <Route path="/invoices/:id" element={<InvoiceDetail />} />
              <Route path="/proposals" element={<Proposals />} />
              <Route path="/proposals/:id" element={<ProposalDetail />} />
              <Route path="/contracts" element={<Contracts />} />
              <Route path="/chat" element={<Chat />} />
              <Route path="/support" element={<Support />} />
              <Route path="/support/:id" element={<TicketDetail />} />
              <Route path="/knowledge-base" element={<KnowledgeBase />} />
              <Route path="/vault" element={<Vault />} />
              <Route path="/files" element={<Files />} />
              <Route path="/automations" element={<Automations />} />
              <Route path="/analytics" element={<Analytics />} />
              <Route path="/settings" element={<Settings />} />
              <Route path="/policies" element={<Policies />} />
              <Route path="/notes" element={<Notes />} />
              <Route path="/help" element={<Help />} />
              <Route path="/calendar" element={<Calendar />} />
              <Route path="/meetings" element={<Navigate to="/calendar" replace />} />
            </Route>

            <Route
              path="/portal"
              element={
                <ProtectedRoute roles={["client"]}>
                  <PortalLayout />
                </ProtectedRoute>
              }
            >
              <Route index element={<PortalDashboard />} />
              <Route path="projects" element={<PortalProjects />} />
              <Route path="projects/:id" element={<PortalProjectDetail />} />
              <Route path="invoices" element={<PortalInvoices />} />
              <Route path="invoices/:id" element={<InvoiceDetail />} />
              <Route path="contracts" element={<PortalContracts />} />
              <Route path="files" element={<PortalFiles />} />
              <Route path="chat" element={<PortalChat />} />
              <Route path="policies" element={<PortalPolicies />} />
              <Route path="support" element={<PortalSupport />} />
              <Route path="support/:id" element={<PortalTicketDetail />} />
            </Route>

            <Route path="*" element={<Navigate to="/login" replace />} />
          </Routes>
          <Toaster />
        </AuthProvider>
      </BrowserRouter>
    </div>
  );
}

export default App;
