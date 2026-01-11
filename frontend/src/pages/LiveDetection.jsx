import { useEffect, useMemo, useState } from "react";
import { fetchAnomalies } from "../services/anomaliesApi";

const STREAM_URL =
  import.meta.env.VITE_MJPEG_STREAM_URL || "http://localhost:8000/stream";

const formatTimestamp = (value) => {
  if (!value) return "No updates yet";
  const date = new Date(value);
  if (Number.isNaN(date.valueOf())) return value;
  return new Intl.DateTimeFormat("en-GB", {
    dateStyle: "medium",
    timeStyle: "medium",
  }).format(date);
};

function LiveDetection() {
  const [anomalies, setAnomalies] = useState([]);
  const [lastUpdated, setLastUpdated] = useState(null);
  const [streamStatus, setStreamStatus] = useState("Connecting");

  useEffect(() => {
    let isMounted = true;

    const load = async () => {
      try {
        const data = await fetchAnomalies();
        if (!isMounted) return;
        setAnomalies(data);
        setLastUpdated(new Date());
      } catch (error) {
        console.error(error);
      }
    };

    load();
    const interval = setInterval(load, 5000);
    return () => {
      isMounted = false;
      clearInterval(interval);
    };
  }, []);

  const feedItems = useMemo(() => {
    return [...anomalies]
      .sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp))
      .slice(0, 10);
  }, [anomalies]);

  return (
    <section className="page">
      <div className="page-header">
        <div>
          <h1>Live Detection</h1>
          <p>Live annotated stream with real-time detection updates.</p>
        </div>
        <span className="status-pill">Live</span>
      </div>

      <div className="grid-two">
        <div className="card">
          <div className="card-header">
            <h2>Live Stream</h2>
            <span className="badge">{streamStatus}</span>
          </div>
          <div className="stream-frame">
            {STREAM_URL ? (
              <img
                src={STREAM_URL}
                alt="Live detection stream"
                onLoad={() => setStreamStatus("Live")}
                onError={() => setStreamStatus("Offline")}
              />
            ) : (
              <p className="muted">Configure the MJPEG stream URL.</p>
            )}
          </div>
          <p className="muted">Stream endpoint: {STREAM_URL}</p>
        </div>

        <div className="stack">
          <div className="card">
            <div className="card-header">
              <h2>System Status</h2>
            </div>
            <div className="status-list">
              <div>
                <p className="label">Stream status</p>
                <p className="value">{streamStatus}</p>
              </div>
              <div>
                <p className="label">Total anomalies detected</p>
                <p className="value">{anomalies.length}</p>
              </div>
              <div>
                <p className="label">Last updated</p>
                <p className="value">{formatTimestamp(lastUpdated)}</p>
              </div>
            </div>
          </div>

          <div className="card">
            <div className="card-header">
              <h2>Detection Feed</h2>
              <span className="badge accent">Live</span>
            </div>
            <div className="feed">
              {feedItems.length === 0 ? (
                <p className="muted">Waiting for detections...</p>
              ) : (
                feedItems.map((item) => (
                  <div className="feed-item" key={item.id}>
                    <div>
                      <p className="feed-title">{item.category}</p>
                      <p className="muted">
                        {item.camera_id} •{" "}
                        {formatTimestamp(item.timestamp)}
                      </p>
                    </div>
                    <span className="badge">
                      {Math.round(item.confidence * 100)}%
                    </span>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

export default LiveDetection;
