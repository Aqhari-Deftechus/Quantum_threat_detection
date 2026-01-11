import { useMemo, useState } from "react";
import AppShell from "./components/layout/AppShell";
import Analysis from "./pages/Analysis";
import Anomalies from "./pages/Anomalies";
import LiveDetection from "./pages/LiveDetection";

const PAGE_COMPONENTS = {
  live: LiveDetection,
  analysis: Analysis,
  anomalies: Anomalies,
};

function App() {
  const [page, setPage] = useState("live");
  const PageComponent = useMemo(() => PAGE_COMPONENTS[page], [page]);

  return (
    <AppShell activePage={page} onNavigate={setPage}>
      <PageComponent />
    </AppShell>
  );
}

export default App;
