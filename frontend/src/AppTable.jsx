// src/AppTable.jsx

import { useEffect, useState } from "react";

function AppTable() {
  const [anomalies, setAnomalies] = useState([]);
  const [loading, setLoading] = useState(true);
  const backendUrl = "http://localhost:8000/api/anomalies";

  useEffect(() => {
    async function fetchAnomalies() {
      try {
        const res = await fetch(backendUrl);
        const data = await res.json();
        setAnomalies(data);
      } catch (err) {
        console.error("Error fetching anomalies:", err);
      } finally {
        setLoading(false);
      }
    }

    fetchAnomalies();
  }, []);

  if (loading) return <p>Loading anomalies...</p>;

  return (
    <div style={{ padding: "20px", fontFamily: "Arial, sans-serif" }}>
      <h1>Quantum Threat Detection</h1>
      <table border="1" cellPadding="10" style={{ borderCollapse: "collapse", width: "100%" }}>
        <thead>
          <tr>
            <th>ID</th>
            <th>Date</th>
            <th>Video</th>
          </tr>
        </thead>
        <tbody>
          {anomalies.map((a) => (
            <tr key={a.anomaly_id}>
              <td>{a.anomaly_id}</td>
              <td>{a.date}</td>
              <td>
                {a.video_url ? (
                  <video
                    width="320"
                    height="240"
                    controls
                    src={`http://localhost:8000${a.video_url}`}
                  >
                    Your browser does not support the video tag.
                  </video>
                ) : (
                  "No video"
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default AppTable;
