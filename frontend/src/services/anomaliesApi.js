import axiosClient from "../api/axiosClient";
import { fetchCameraAnomalies, listCameras } from "./monitoringApi";

export const resolveAssetUrl = (url) => {
  if (!url) return "";
  if (url.startsWith("http://") || url.startsWith("https://")) return url;
  const baseUrl = axiosClient.defaults.baseURL?.replace(/\/$/, "") || "";
  return `${baseUrl}${url.startsWith("/") ? "" : "/"}${url}`;
};

export const normalizeAnomaly = (item, cameraIdFallback) => ({
  id:
    item.incident_id ??
    item.anomaly_id ??
    item.id ??
    `${item.timestamp}-${cameraIdFallback || "unknown"}`,
  timestamp: item.timestamp ?? item.date ?? "",
  camera_id: item.camera_id ?? item.camera ?? cameraIdFallback ?? "Unknown",
  category: item.category ?? item.type ?? "Uncategorized",
  confidence: Number(item.confidence ?? item.similarity ?? 0),
  thumbnail_url: item.thumbnail_url ?? item.image_url ?? "",
  video_url: item.video_url ?? "",
});

export async function fetchAnomalies() {
  const cameras = await listCameras();
  if (!cameras.length) return [];

  const results = await Promise.all(
    cameras.map(async (cameraId) => {
      const data = await fetchCameraAnomalies(cameraId);
      return data.map((item) => normalizeAnomaly(item, cameraId));
    })
  );

  return results.flat();
}
