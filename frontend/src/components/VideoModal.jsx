import React from "react";
import Modal from "react-modal";

Modal.setAppElement("#root");

function VideoModal({ video, onClose }) {
  return (
    <Modal isOpen={!!video} onRequestClose={onClose} contentLabel="Video Modal">
      <button onClick={onClose}>Close</button>
      <video src={video} controls width="100%"></video>
    </Modal>
  );
}

export default VideoModal;
