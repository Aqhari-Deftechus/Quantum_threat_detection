import React from "react";

function IncidentTable({ incidents, onVideoClick }) {
  return (
    <table>
      <thead>
        <tr>
          <th>ID</th>
          <th>Type</th>
          <th>Time</th>
          <th>Video</th>
        </tr>
      </thead>
      <tbody>
        {incidents.map((inc) => (
          <tr key={inc.id}>
            <td>{inc.id}</td>
            <td>{inc.type}</td>
            <td>{inc.time}</td>
            <td>
              <button onClick={() => onVideoClick(inc.video_url)}>
                Play
              </button>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export default IncidentTable;
