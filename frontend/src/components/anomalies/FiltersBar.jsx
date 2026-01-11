function FiltersBar({
  search,
  onSearchChange,
  category,
  onCategoryChange,
  camera,
  onCameraChange,
  categories,
  cameras,
  confidenceRange,
  onConfidenceChange,
}) {
  const handleMinChange = (value) => {
    const nextMin = Math.min(value, confidenceRange[1]);
    onConfidenceChange([nextMin, confidenceRange[1]]);
  };

  const handleMaxChange = (value) => {
    const nextMax = Math.max(value, confidenceRange[0]);
    onConfidenceChange([confidenceRange[0], nextMax]);
  };

  return (
    <div className="filters">
      <div className="filter-row">
        <label className="field">
          <span>Search</span>
          <input
            value={search}
            onChange={(event) => onSearchChange(event.target.value)}
            placeholder="Incident ID, category, camera..."
          />
        </label>
        <label className="field">
          <span>Category</span>
          <select
            value={category}
            onChange={(event) => onCategoryChange(event.target.value)}
          >
            <option value="all">All</option>
            {categories.map((item) => (
              <option key={item} value={item}>
                {item}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          <span>Camera</span>
          <select
            value={camera}
            onChange={(event) => onCameraChange(event.target.value)}
          >
            <option value="all">All</option>
            {cameras.map((item) => (
              <option key={item} value={item}>
                {item}
              </option>
            ))}
          </select>
        </label>
      </div>
      <div className="filter-row">
        <label className="field full">
          <span>
            Confidence range (%): {confidenceRange[0]} - {confidenceRange[1]}
          </span>
          <input
            type="range"
            min="0"
            max="100"
            value={confidenceRange[0]}
            onChange={(event) =>
              handleMinChange(Number(event.target.value))
            }
          />
          <input
            type="range"
            min="0"
            max="100"
            value={confidenceRange[1]}
            onChange={(event) =>
              handleMaxChange(Number(event.target.value))
            }
          />
        </label>
      </div>
    </div>
  );
}

export default FiltersBar;
