// src/App.jsx

import { useState } from "react";
import AppTable from "./AppTable";
import LiveDetection from "./LiveDetection"; // your new live detection component

function App() {
  const [page, setPage] = useState(1); // 1 = live, 2 = table

  return (
    <div>
      <nav style={{ marginBottom: "20px" }}>
        <button onClick={() => setPage(1)}>Live Detection</button>
        <button onClick={() => setPage(2)}>Anomalies Table</button>
      </nav>

      {page === 1 ? <LiveDetection /> : <AppTable />}
    </div>
  );
}

export default App;
