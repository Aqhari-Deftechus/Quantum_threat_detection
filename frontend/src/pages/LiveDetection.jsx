import { useEffect, useMemo, useRef, useState } from "react";
import {
  addCamera,
  buildStreamUrl,
  checkHealth,
  deleteCamera,
  fetchCameraAnomalies,
  fetchCameraFaces,
  listCameras,
  startCamera,
  stopCamera,
  subscribeToEvents,
  testCameraConnection,
} from "../services/monitoringApi";

const formatTimestamp = (value) => {
  if (!value) return "No updates yet";
  const date = new Date(value);
  if (Number.isNaN(date.valueOf())) return value;
  return new Intl.DateTimeFormat("en-GB", {
    dateStyle: "medium",
    timeStyle: "medium",
  }).format(date);
};

const defaultCameraForm = {
  camera_id: "",
  source: "",
};

const parseSource = (value) => {
  const trimmed = value.trim();
  if (/^\d+$/.test(trimmed)) {
    return Number(trimmed);
  }
  return trimmed;
};

function LiveDetection() {
  const [health, setHealth] = useState({ status: "unknown" });
  const [cameras, setCameras] = useState([]);
  const [activeCamera, setActiveCamera] = useState("");
  const [cameraForm, setCameraForm] = useState(defaultCameraForm);
  const [connectionStatus, setConnectionStatus] = useState("Idle");
  const [streamStatus, setStreamStatus] = useState("Connecting");
  const [latestFace, setLatestFace] = useState(null);
  const [latestAnomalies, setLatestAnomalies] = useState([]);
  const [events, setEvents] = useState([]);
  const [lastUpdated, setLastUpdated] = useState(null);
  const streamImgRef = useRef(null);
  const overlayRef = useRef(null);

  useEffect(() => {
    let mounted = true;

    const load = async () => {
      try {
        const [healthData, cameraList] = await Promise.all([
          checkHealth(),
          listCameras(),
        ]);
        if (!mounted) return;
        setHealth(healthData);
        setCameras(cameraList);
        if (!activeCamera && cameraList.length) {
          setActiveCamera(cameraList[0]);
        }
      } catch (error) {
        console.error(error);
      }
    };

    load();
    return () => {
      mounted = false;
    };
  }, [activeCamera]);

  useEffect(() => {
    if (!activeCamera) return undefined;
    let mounted = true;
    const refresh = async () => {
      try {
        const [face, anomalies] = await Promise.all([
          fetchCameraFaces(activeCamera),
          fetchCameraAnomalies(activeCamera),
        ]);

        if (mounted) {
          setLatestFace(face);
          setLatestAnomalies(anomalies);
          setLastUpdated(new Date());
        }
      } catch (error) {
        console.error(error);
      }
    };
    refresh();
    const interval = setInterval(refresh, 3000);
    return () => {
      mounted = false;
      clearInterval(interval);
    };
  }, [activeCamera]);

  useEffect(() => {
    const eventSource = subscribeToEvents((payload) => {
      setEvents((prev) => [payload, ...prev].slice(0, 20));
    });
    return () => {
      eventSource.close();
    };
  }, []);

  const streamUrl = useMemo(
    () => buildStreamUrl(activeCamera, 6),
    [activeCamera]
  );

  const handleAddCamera = async (event) => {
    event.preventDefault();
    if (!cameraForm.camera_id || !cameraForm.source) return;

    try {
      setConnectionStatus("Testing...");
      const parsedSource = parseSource(cameraForm.source);
      await testCameraConnection(parsedSource);
      setConnectionStatus("Connected");
      await addCamera({
        camera_id: cameraForm.camera_id,
        source: parsedSource,
      });

      await startCamera(cameraForm.camera_id);
      const updated = await listCameras();
      setCameras(updated);
      setActiveCamera(cameraForm.camera_id);
      setCameraForm(defaultCameraForm);
    } catch (error) {
      console.error(error);
      setConnectionStatus("Failed");
    }
  };

  const handleStart = async (cameraId) => {
    await startCamera(cameraId);
  };

  const handleStop = async (cameraId) => {
    await stopCamera(cameraId);
  };

  const handleDelete = async (cameraId) => {
    await deleteCamera(cameraId);
    const updated = await listCameras();
    setCameras(updated);
    if (cameraId === activeCamera) {
      setActiveCamera(updated[0] || "");
    }
  };

  const activeEvents = events.filter((event) => event.camera_id === activeCamera);

  useEffect(() => {
    const canvas = overlayRef.current;
    const image = streamImgRef.current;
    if (!canvas || !image) return;

    const width = image.clientWidth;
    const height = image.clientHeight;
    if (!width || !height) return;

    canvas.width = width;
    canvas.height = height;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    ctx.clearRect(0, 0, width, height);
    activeEvents.forEach((event) => {
      if (!event.bbox || !event.frame_width || !event.frame_height) return;
      const [x, y, w, h] = event.bbox;
      const scaleX = width / event.frame_width;
      const scaleY = height / event.frame_height;
      const left = x * scaleX;
      const top = y * scaleY;
      const boxW = w * scaleX;
      const boxH = h * scaleY;
      const color = event.auth ? "#00e676" : "#ffb300";

      ctx.strokeStyle = color;
      ctx.lineWidth = 2;
      ctx.strokeRect(left, top, boxW, boxH);

      const label = `${event.name || "Unknown"} (${Math.round(
        event.similarity || 0
      )}%)`;
      ctx.fillStyle = color;
      ctx.font = "14px Inter, sans-serif";
      ctx.fillText(label, left, Math.max(top - 8, 16));
    });
  }, [activeEvents, streamStatus, streamUrl]);

  return (
    <section className="page">
      <div className="page-header">
        <div>
          <h1>Live Detection</h1>
          <p>Live annotated stream with real-time detection updates.</p>
        </div>
        <span className="status-pill">
          API: {health.status === "ok" ? "Online" : "Offline"}
        </span>
      </div>

      <div className="grid-two">
        <div className="card">
          <div className="card-header">
            <h2>Live Stream</h2>
            <span className="badge">{streamStatus}</span>
          </div>
          <div className="stream-frame">
            {streamUrl ? (
              <div className="stream-layer">
                <img
                  ref={streamImgRef}
                  src={streamUrl}
                  alt="Live detection stream"
                  onLoad={() => setStreamStatus("Live")}
                  onError={() => setStreamStatus("Offline")}
                />
                <canvas ref={overlayRef} className="stream-canvas" />
              </div>
            ) : (
              <p className="muted">Select a camera to start streaming.</p>
            )}
          </div>
          <p className="muted">Stream endpoint: {streamUrl || "—"}</p>
        </div>

        <div className="stack">
          <div className="card">
            <div className="card-header">
              <h2>Camera Control</h2>
              <span className="badge accent">{connectionStatus}</span>
            </div>
            <form className="form-grid" onSubmit={handleAddCamera}>
              <label className="field">
                <span>Camera ID</span>
                <input
                  value={cameraForm.camera_id}
                  onChange={(event) =>
                    setCameraForm((prev) => ({
                      ...prev,
                      camera_id: event.target.value,
                    }))
                  }
                  placeholder="cam-01"
                />
              </label>
              <label className="field">
                <span>Source (Webcam index or RTSP URL)</span>
                <input
                  value={cameraForm.source}
                  onChange={(event) =>
                    setCameraForm((prev) => ({
                      ...prev,
                      source: event.target.value,
                    }))
                  }
                  placeholder="0 or rtsp://user:pass@ip/stream"
                />
              </label>
              <div className="form-actions">
                <button type="submit" className="primary-button">
                  Test + Add Camera
                </button>
                <p className="muted">
                  Use <strong>0</strong> for local webcam in the backend host.
                </p>
              </div>
            </form>

            <div className="camera-list">
              {cameras.length === 0 ? (
                <p className="muted">No cameras configured.</p>
              ) : (
                cameras.map((cameraId) => (
                  <div
                    key={cameraId}
                    className={`camera-item ${
                      activeCamera === cameraId ? "active" : ""
                    }`}
                  >
                    <button
                      type="button"
                      className="link-button"
                      onClick={() => setActiveCamera(cameraId)}
                    >
                      {cameraId}
                    </button>
                    <div className="camera-actions">
                      <button
                        type="button"
                        className="secondary-button"
                        onClick={() => handleStart(cameraId)}
                      >
                        Start
                      </button>
                      <button
                        type="button"
                        className="secondary-button"
                        onClick={() => handleStop(cameraId)}
                      >
                        Stop
                      </button>
                      <button
                        type="button"
                        className="danger-button"
                        onClick={() => handleDelete(cameraId)}
                      >
                        Delete
                      </button>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>

          <div className="card">
            <div className="card-header">
              <h2>Latest Recognition</h2>
            </div>
            <div className="status-list">
              <div>
                <p className="label">Camera</p>
                <p className="value">{activeCamera || "None"}</p>
              </div>
              <div>
                <p className="label">Identity</p>
                <p className="value">{latestFace?.name || "—"}</p>
              </div>
              <div>
                <p className="label">Anomalies</p>
                <p className="value">
                  {latestAnomalies.length
                    ? `${latestAnomalies.length} detected`
                    : "None"}
                </p>
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
              <span className="badge accent">SSE Live</span>
            </div>
            <div className="feed">
              {activeEvents.length === 0 ? (
                <p className="muted">Waiting for detections...</p>
              ) : (
                activeEvents.map((item, index) => (
                  <div className="feed-item" key={`${item.camera_id}-${index}`}>
                    <div>
                      <p className="feed-title">{item.name || "Unknown"}</p>
                      <p className="muted">
                        {item.camera_id} • {formatTimestamp(item.timestamp)}
                      </p>
                      <p className="muted">
                        BBox: {item.bbox ? item.bbox.join(", ") : "—"}
                      </p>
                    </div>
                    <span className="badge">
                      {Math.round(item.similarity || 0)}%
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
