import { useEffect, useMemo, useState } from "react";
import FiltersBar from "../components/anomalies/FiltersBar";
import AnomaliesTable from "../components/anomalies/AnomaliesTable";
import PreviewModal from "../components/anomalies/PreviewModal";
import { fetchAnomalies } from "../services/anomaliesApi";

function Anomalies() {
  const [anomalies, setAnomalies] = useState([]);
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState("all");
  const [camera, setCamera] = useState("all");
  const [confidenceRange, setConfidenceRange] = useState([0, 100]);
  const [selected, setSelected] = useState(null);

  useEffect(() => {
    fetchAnomalies().then(setAnomalies).catch(console.error);
  }, []);

  const categories = useMemo(
    () =>
      Array.from(new Set(anomalies.map((item) => item.category))).filter(Boolean),
    [anomalies]
  );

  const cameras = useMemo(
    () =>
      Array.from(new Set(anomalies.map((item) => item.camera_id))).filter(
        Boolean
      ),
    [anomalies]
  );

  const filtered = useMemo(() => {
    return anomalies.filter((item) => {
      const matchesSearch =
        search.trim() === "" ||
        item.id.toString().includes(search) ||
        item.category.toLowerCase().includes(search.toLowerCase()) ||
        item.camera_id.toLowerCase().includes(search.toLowerCase());
      const matchesCategory =
        category === "all" || item.category === category;
      const matchesCamera = camera === "all" || item.camera_id === camera;
      const confidence = item.confidence * 100;
      const matchesConfidence =
        confidence >= confidenceRange[0] &&
        confidence <= confidenceRange[1];
      return (
        matchesSearch && matchesCategory && matchesCamera && matchesConfidence
      );
    });
  }, [anomalies, search, category, camera, confidenceRange]);

  return (
    <section className="page">
      <div className="page-header">
        <div>
          <h1>Anomalies</h1>
          <p>
            Filter and review incidents, preview footage, and export for
            reporting.
          </p>
        </div>
      </div>

      <div className="card">
        <FiltersBar
          search={search}
          onSearchChange={setSearch}
          category={category}
          onCategoryChange={setCategory}
          camera={camera}
          onCameraChange={setCamera}
          categories={categories}
          cameras={cameras}
          confidenceRange={confidenceRange}
          onConfidenceChange={setConfidenceRange}
        />
      </div>

      <div className="card">
        <AnomaliesTable items={filtered} onPreview={setSelected} />
      </div>

      <PreviewModal
        open={Boolean(selected)}
        item={selected}
        onClose={() => setSelected(null)}
      />
    </section>
  );
}

export default Anomalies;
