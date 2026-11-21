import { BrowserRouter, Route, Routes } from "react-router-dom";
import { Shell } from "./components/Shell";
import { AuditLog } from "./pages/AuditLog";
import { CaseView } from "./pages/CaseView";
import { Dashboard } from "./pages/Dashboard";
import { How } from "./pages/How";
import { Institutions } from "./pages/Institutions";
import { Queue } from "./pages/Queue";
import { Runs } from "./pages/Runs";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Shell />}>
          <Route index element={<Queue />} />
          <Route path="dashboard" element={<Dashboard />} />
          <Route path="institutions" element={<Institutions />} />
          <Route path="cases/:institution/:caseId" element={<CaseView />} />
          <Route path="runs" element={<Runs />} />
          <Route path="docs" element={<How />} />
          <Route path="models" element={<How />} />
          <Route path="audit" element={<AuditLog />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
