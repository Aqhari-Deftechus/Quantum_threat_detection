import { resolveAssetUrl } from "../../services/anomaliesApi";

const formatTime = (value) => {
  if (!value) return "Unknown";
  const date = new Date(value);
  if (Number.isNaN(date.valueOf())) return value;
  return new Intl.DateTimeFormat("en-GB", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
};

function AnomaliesTable({ items, onPreview }) {
  if (!items.length) {
    return <p className="muted">No anomalies found for the selected filters.</p>;
  }

  return (
    <div className="table-wrapper">
      <table>
        <thead>
          <tr>
            <th>Incident ID</th>
            <th>Timestamp</th>
            <th>Camera</th>
            <th>Category</th>
            <th>Confidence</th>
            <th>Preview</th>
          </tr>
        </thead>
        <tbody>
          {items.map((item) => (
            <tr key={item.id}>
              <td>{item.id}</td>
              <td>{formatTime(item.timestamp)}</td>
              <td>{item.camera_id}</td>
              <td>
                <span className="badge">{item.category}</span>
              </td>
              <td>{Math.round(item.confidence * 100)}%</td>
              <td>
                <div className="preview-cell">
                  {item.thumbnail_url && (
                    <img
                      src={resolveAssetUrl(item.thumbnail_url)}
                      alt="thumbnail"
                    />
                  )}
                  <button
                    type="button"
                    className="secondary-button"
                    onClick={() => onPreview(item)}
                  >
                    View
                  </button>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default AnomaliesTable;
