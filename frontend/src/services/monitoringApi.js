import axiosClient from "../api/axiosClient";

const API_PREFIX = "/api";

const getApiUrl = (path) => `${API_PREFIX}${path}`;

export const checkHealth = async () => {
  const response = await axiosClient.get(getApiUrl("/health"));
  return response.data;
};

export const listCameras = async () => {
  const response = await axiosClient.get(getApiUrl("/cameras"));
  return response.data?.cameras || [];
};

export const addCamera = async ({ camera_id, source }) => {
  const response = await axiosClient.post(getApiUrl("/cameras"), {
    camera_id,
    source,
  });
  return response.data;
};

export const startCamera = async (cameraId) => {
  const response = await axiosClient.post(
    getApiUrl(`/cameras/${cameraId}/start`)
  );
  return response.data;
};

export const stopCamera = async (cameraId) => {
  const response = await axiosClient.post(
    getApiUrl(`/cameras/${cameraId}/stop`)
  );
  return response.data;
};

export const deleteCamera = async (cameraId) => {
  const response = await axiosClient.delete(getApiUrl(`/cameras/${cameraId}`));
  return response.data;
};

export const testCameraConnection = async (source) => {
  const response = await axiosClient.post(
    getApiUrl("/cameras/test-connection"),
    { source }
  );
  return response.data;
};

export const fetchCameraFaces = async (cameraId) => {
  const response = await axiosClient.get(getApiUrl(`/cameras/${cameraId}/faces`));
  return response.data || {};
};

export const fetchCameraAnomalies = async (cameraId) => {
  const response = await axiosClient.get(
    getApiUrl(`/cameras/${cameraId}/anomalies`)
  );
  const data = response.data;
  if (!data) return [];
  if (Array.isArray(data)) return data;
  if (Array.isArray(data.anomalies)) return data.anomalies;
  return [];
};

export const buildStreamUrl = (cameraId, fps = 5) => {
  if (!cameraId) return "";
  const baseUrl = axiosClient.defaults.baseURL?.replace(/\/$/, "") || "";
  return `${baseUrl}${getApiUrl(`/cameras/${cameraId}/stream`)}?fps=${fps}`;
};

export const subscribeToEvents = (onMessage) => {
  const baseUrl = axiosClient.defaults.baseURL?.replace(/\/$/, "") || "";
  const eventSource = new EventSource(`${baseUrl}${getApiUrl("/events/stream")}`);
  eventSource.onmessage = (event) => {
    try {
      onMessage(JSON.parse(event.data));
    } catch (error) {
      console.error("Failed to parse event stream payload", error);
    }
  };
  return eventSource;
};
