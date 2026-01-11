import Modal from "react-modal";
import { resolveAssetUrl } from "../../services/anomaliesApi";

Modal.setAppElement("#root");

function PreviewModal({ open, item, onClose }) {
  if (!item) return null;

  return (
    <Modal
      isOpen={open}
      onRequestClose={onClose}
      className="modal"
      overlayClassName="modal-overlay"
    >
      <div className="modal-header">
        <h2>Incident {item.id}</h2>
        <button type="button" className="secondary-button" onClick={onClose}>
          Close
        </button>
      </div>
      <p className="muted">
        {item.category} • {item.camera_id}
      </p>
      {item.video_url ? (
        <video controls src={resolveAssetUrl(item.video_url)} />
      ) : item.thumbnail_url ? (
        <img src={resolveAssetUrl(item.thumbnail_url)} alt="Anomaly thumbnail" />
      ) : (
        <p className="muted">No preview available.</p>
      )}
    </Modal>
  );
}

export default PreviewModal;
