import axios from "axios";

const axiosClient = axios.create({
  baseURL: "http://localhost:8000", // Flask backend
});

export default axiosClient;
