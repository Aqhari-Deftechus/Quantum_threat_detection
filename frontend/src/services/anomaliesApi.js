const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

export const DEFAULT_ANOMALIES_ENDPOINT = `${API_BASE_URL}/api/anomalies`;

export const resolveAssetUrl = (url) => {
  if (!url) return "";
  if (url.startsWith("http://") || url.startsWith("https://")) return url;
  return `${API_BASE_URL}${url.startsWith("/") ? "" : "/"}${url}`;
};

export const normalizeAnomaly = (item) => ({
  id: item.incident_id ?? item.anomaly_id ?? item.id ?? `${item.timestamp}`,
  timestamp: item.timestamp ?? item.date ?? "",
  camera_id: item.camera_id ?? item.camera ?? "Unknown",
  category: item.category ?? item.type ?? "Uncategorized",
  confidence: Number(item.confidence ?? item.similarity ?? 0),
  thumbnail_url: item.thumbnail_url ?? item.image_url ?? "",
  video_url: item.video_url ?? "",
});

export async function fetchAnomalies() {
  const response = await fetch(DEFAULT_ANOMALIES_ENDPOINT);
  if (!response.ok) {
    throw new Error(`Failed to fetch anomalies: ${response.status}`);
  }
  const data = await response.json();
  return Array.isArray(data) ? data.map(normalizeAnomaly) : [];
}
