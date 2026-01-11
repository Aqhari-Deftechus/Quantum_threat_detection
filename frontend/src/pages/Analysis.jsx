import { useEffect, useMemo, useState } from "react";
import { fetchAnomalies } from "../services/anomaliesApi";

const formatBucket = (value) => {
  const date = new Date(value);
  if (Number.isNaN(date.valueOf())) return "Unknown";
  return `${date.getHours().toString().padStart(2, "0")}:00`;
};

const formatTimestamp = (value) => {
  if (!value) return "No data";
  const date = new Date(value);
  if (Number.isNaN(date.valueOf())) return value;
  return new Intl.DateTimeFormat("en-GB", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
};

function Analysis() {
  const [anomalies, setAnomalies] = useState([]);

  useEffect(() => {
    let isMounted = true;
    fetchAnomalies()
      .then((data) => {
        if (isMounted) {
          setAnomalies(data);
        }
      })
      .catch(console.error);
    return () => {
      isMounted = false;
    };
  }, []);

  const summary = useMemo(() => {
    if (!anomalies.length) {
      return {
        total: 0,
        avgConfidence: 0,
        topCategory: "N/A",
        latest: "No data",
      };
    }

    const totalConfidence = anomalies.reduce(
      (sum, item) => sum + (item.confidence || 0),
      0
    );
    const avgConfidence = totalConfidence / anomalies.length;

    const categoryCount = anomalies.reduce((acc, item) => {
      acc[item.category] = (acc[item.category] || 0) + 1;
      return acc;
    }, {});
    const topCategory =
      Object.entries(categoryCount).sort((a, b) => b[1] - a[1])[0]?.[0] || "N/A";

    const latest = anomalies
      .map((item) => item.timestamp)
      .filter(Boolean)
      .sort()
      .slice(-1)[0];

    return {
      total: anomalies.length,
      avgConfidence: avgConfidence * 100,
      topCategory,
      latest,
    };
  }, [anomalies]);

  const timeSeries = useMemo(() => {
    const buckets = anomalies.reduce((acc, item) => {
      const key = formatBucket(item.timestamp);
      acc[key] = (acc[key] || 0) + 1;
      return acc;
    }, {});
    return Object.entries(buckets)
      .map(([bucket, count]) => ({ bucket, count }))
      .sort((a, b) => a.bucket.localeCompare(b.bucket));
  }, [anomalies]);

  const categorySeries = useMemo(() => {
    const buckets = anomalies.reduce((acc, item) => {
      acc[item.category] = (acc[item.category] || 0) + 1;
      return acc;
    }, {});
    return Object.entries(buckets).map(([category, count]) => ({
      category,
      count,
    }));
  }, [anomalies]);

  const linePoints = useMemo(() => {
    if (!timeSeries.length) return "";
    const max = Math.max(...timeSeries.map((item) => item.count), 1);
    return timeSeries
      .map((item, index) => {
        const x = (index / (timeSeries.length - 1 || 1)) * 280 + 20;
        const y = 120 - (item.count / max) * 90 + 20;
        return `${x},${y}`;
      })
      .join(" ");
  }, [timeSeries]);

  return (
    <section className="page">
      <div className="page-header">
        <div>
          <h1>Analysis</h1>
          <p>Insights derived from the anomaly stream.</p>
        </div>
      </div>

      <div className="kpi-grid">
        <div className="card kpi-card">
          <p className="label">Total anomalies</p>
          <p className="value">{summary.total}</p>
        </div>
        <div className="card kpi-card">
          <p className="label">Average confidence</p>
          <p className="value">{summary.avgConfidence.toFixed(1)}%</p>
        </div>
        <div className="card kpi-card">
          <p className="label">Top category</p>
          <p className="value">{summary.topCategory}</p>
        </div>
        <div className="card kpi-card">
          <p className="label">Latest incident</p>
          <p className="value">{formatTimestamp(summary.latest)}</p>
        </div>
      </div>

      <div className="grid-two">
        <div className="card">
          <div className="card-header">
            <h2>Anomalies Over Time</h2>
          </div>
          {timeSeries.length === 0 ? (
            <p className="muted">No anomaly data yet.</p>
          ) : (
            <>
              <svg viewBox="0 0 320 160" className="line-chart">
                <polyline points={linePoints} />
              </svg>
              <div className="chart-labels">
                {timeSeries.map((item) => (
                  <span key={item.bucket}>{item.bucket}</span>
                ))}
              </div>
            </>
          )}
        </div>
        <div className="card">
          <div className="card-header">
            <h2>Anomalies by Category</h2>
          </div>
          {categorySeries.length === 0 ? (
            <p className="muted">No anomaly data yet.</p>
          ) : (
            <div className="bar-chart">
              {categorySeries.map((item) => (
                <div key={item.category} className="bar-row">
                  <span>{item.category}</span>
                  <div className="bar-track">
                    <div
                      className="bar-fill"
                      style={{
                        width: `${Math.min(item.count * 20, 100)}%`,
                      }}
                    />
                  </div>
                  <span className="bar-value">{item.count}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </section>
  );
}

export default Analysis;
