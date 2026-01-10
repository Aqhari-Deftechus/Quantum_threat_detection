// src/LiveDetectionReactive.jsx
import { useEffect, useRef, useState } from "react";

function LiveDetectionReactive() {
  const [cameras, setCameras] = useState([]);
  const [selectedCamera, setSelectedCamera] = useState("");
  const [events, setEvents] = useState([]);
  const [snapshots, setSnapshots] = useState([]);
  const [faces, setFaces] = useState([]);
  const [anomalies, setAnomalies] = useState([]);
  const [newCameraId, setNewCameraId] = useState("");
  const [newCameraSource, setNewCameraSource] = useState("");

  const videoRef = useRef(null);
  const canvasRef = useRef(null);

  // --- Load cameras ---
  const loadCameras = (autoSelectNew = true) => {
    fetch("http://localhost:8000/api/cameras")
      .then((res) => res.json())
      .then((data) => {
        const camList = data.cameras || [];
        setCameras(camList);
        if (autoSelectNew && camList.length > 0) {
          setSelectedCamera(
            camList[camList.length - 1].id || camList[camList.length - 1]
          );
        }
      })
      .catch(console.error);
  };

  useEffect(() => {
    loadCameras();
  }, []);

  // --- Add new camera ---
  const handleAddCamera = () => {
    if (!newCameraId || !newCameraSource)
      return alert("Camera ID and Source required");

    fetch("http://localhost:8000/api/cameras", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ camera_id: newCameraId, source: newCameraSource }),
    })
      .then((res) => res.json())
      .then((data) => {
        console.log("Camera added:", data);
        setNewCameraId("");
        setNewCameraSource("");
        loadCameras();
      })
      .catch(console.error);
  };

  // --- Camera actions ---
  const handleCameraAction = (cameraId, action) => {
    if (!cameraId) return;
    let url = `http://localhost:8000/api/cameras/${cameraId}`;
    let method = "POST";
    if (action === "delete") method = "DELETE";
    else url += `/${action}`;

    fetch(url, { method })
      .then((res) => res.json())
      .then((data) => {
        console.log("Camera action:", data);
        loadCameras(false);
        if (action === "delete" && cameraId === selectedCamera) {
          setSelectedCamera("");
        }
      })
      .catch(console.error);
  };

  // --- Fetch snapshots, faces, anomalies ---
  useEffect(() => {
    if (!selectedCamera) return;

    const fetchData = () => {
      fetch(`http://localhost:8000/api/cameras/${selectedCamera}/snapshots`)
        .then((res) => res.json())
        .then((data) => setSnapshots(data || []))
        .catch(console.error);

      fetch("http://localhost:8000/api/faces")
        .then((res) => res.json())
        .then((data) => setFaces(data || []))
        .catch(console.error);

      fetch("http://localhost:8000/api/anomalies")
        .then((res) => res.json())
        .then((data) => setAnomalies(data || []))
        .catch(console.error);
    };

    fetchData();
    const interval = setInterval(fetchData, 2000);
    return () => clearInterval(interval);
  }, [selectedCamera]);

  // --- SSE Events ---
  useEffect(() => {
    const evtSource = new EventSource("http://localhost:8000/api/events/stream");
    evtSource.onmessage = (e) => {
      try {
        const data = JSON.parse(e.data);
        setEvents((prev) => [data, ...prev].slice(0, 10));
      } catch (err) {
        console.error("SSE parse error:", err);
      }
    };
    evtSource.onerror = (err) => {
      console.error("SSE error:", err);
      evtSource.close();
    };
    return () => evtSource.close();
  }, []);

  // --- Draw bounding boxes on canvas ---
  useEffect(() => {
    const canvas = canvasRef.current;
    const video = videoRef.current;
    if (!canvas || !video) return;
    const ctx = canvas.getContext("2d");

    const draw = () => {
      if (!video.paused && !video.ended) {
        canvas.width = video.videoWidth;
        canvas.height = video.videoHeight;
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        ctx.drawImage(video, 0, 0, canvas.width, canvas.height);

        const drawBoxes = (items, color, labelFn) => {
          items.forEach((item) => {
            if (!item.bbox) return;
            let [x, y, w, h] = item.bbox;

            if (item.frame_width && item.frame_height) {
              const scaleX = canvas.width / item.frame_width;
              const scaleY = canvas.height / item.frame_height;
              x *= scaleX;
              y *= scaleY;
              w *= scaleX;
              h *= scaleY;
            }

            ctx.strokeStyle = color;
            ctx.lineWidth = 2;
            ctx.strokeRect(x, y, w, h);

            ctx.fillStyle = color;
            ctx.font = "16px Arial";
            ctx.fillText(labelFn(item), x, y - 5);
          });
        };

        drawBoxes(events, "red", (ev) => `${ev.name} (${ev.similarity}%)`);
        drawBoxes(faces, "blue", (f) => f.name);
        drawBoxes(anomalies, "orange", (a) => `ANOMALY: ${a.type}`);
      }
      requestAnimationFrame(draw);
    };

    draw();
  }, [events, faces, anomalies]);

  return (
    <div style={{ padding: 20, fontFamily: "Arial, sans-serif" }}>
      <h1>Live Detection Reactive Dashboard</h1>

      {/* Add Camera */}
      <div style={{ marginBottom: 20 }}>
        <h3>Add New Camera</h3>
        <input
          placeholder="Camera ID"
          value={newCameraId}
          onChange={(e) => setNewCameraId(e.target.value)}
        />
        <input
          placeholder="Source (RTSP / URL)"
          value={newCameraSource}
          onChange={(e) => setNewCameraSource(e.target.value)}
        />
        <button onClick={handleAddCamera}>Add Camera</button>
      </div>

      {/* Camera Controls */}
      <div>
        <label>Select Camera: </label>
        <select
          value={selectedCamera}
          onChange={(e) => setSelectedCamera(e.target.value)}
        >
          {cameras.map((cam) => (
            <option key={cam.id || cam} value={cam.id || cam}>
              {cam.id || cam}
            </option>
          ))}
        </select>

        <button onClick={() => handleCameraAction(selectedCamera, "start")}>
          Start
        </button>
        <button onClick={() => handleCameraAction(selectedCamera, "stop")}>
          Stop
        </button>
        <button onClick={() => handleCameraAction(selectedCamera, "delete")}>
          Delete
        </button>
      </div>

      {/* Video */}
      {selectedCamera && (
        <div
          style={{
            position: "relative",
            display: "inline-block",
            marginTop: 20,
          }}
        >
          <img
            ref={videoRef}
            src={`http://localhost:8000/api/cameras/${selectedCamera}/stream?fps=10`}
            width={640}
            height={480}
            autoPlay
            muted
            playsInline
          />
          <canvas
            ref={canvasRef}
            style={{
              position: "absolute",
              top: 0,
              left: 0,
              pointerEvents: "none",
            }}
          />
        </div>
      )}

      <h3>Latest Events</h3>
      <ul>
        {events.map((ev, idx) => (
          <li key={idx}>
            <strong>{ev.camera_id}</strong> | {ev.name} | Auth: {ev.auth} |{" "}
            Similarity: {ev.similarity}%
          </li>
        ))}
      </ul>

      <h3>Snapshots</h3>
      <ul>
        {snapshots.map((s) => (
          <li key={s.id}>
            <a href={s.url} target="_blank" rel="noreferrer">
              {s.timestamp || s.id}
            </a>
          </li>
        ))}
      </ul>

      <h3>Registered Faces</h3>
      <ul>
        {faces.map((f) => (
          <li key={f.id}>
            {f.name} |{" "}
            <a href={f.image_url} target="_blank" rel="noreferrer">
              View
            </a>
          </li>
        ))}
      </ul>

      <h3>Anomalies</h3>
      <ul>
        {anomalies.map((a) => (
          <li key={a.id}>
            {a.type} |{" "}
            <a href={a.video_url} target="_blank" rel="noreferrer">
              View Video
            </a>
          </li>
        ))}
      </ul>
    </div>
  );
}

export default LiveDetectionReactive;
