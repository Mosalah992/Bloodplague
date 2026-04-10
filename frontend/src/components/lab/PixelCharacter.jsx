import React, { memo, useMemo } from "react";

function PixelCharacterInner({ frame, cellSize = 4, className = "", scale = 1 }) {
  const { width, height, flat } = useMemo(() => {
    if (!frame?.length) return { width: 0, height: 0, flat: [] };
    const h = frame.length;
    const w = frame[0]?.length || 0;
    const cells = [];
    for (let ri = 0; ri < h; ri += 1) {
      const row = frame[ri] || [];
      for (let ci = 0; ci < w; ci += 1) {
        cells.push(row[ci] || null);
      }
    }
    return { width: w, height: h, flat: cells };
  }, [frame]);

  if (!width) return null;

  return (
    <div
      className={`pixel-crisp inline-block ${className}`.trim()}
      style={{
        transform: `scale(${scale})`,
        transformOrigin: "bottom center"
      }}
    >
      <div
        className="grid gap-0"
        style={{
          gridTemplateColumns: `repeat(${width}, ${cellSize}px)`,
          gridTemplateRows: `repeat(${height}, ${cellSize}px)`,
          width: width * cellSize,
          height: height * cellSize
        }}
      >
        {flat.map((color, i) => (
          <div
            key={i}
            style={{
              width: cellSize,
              height: cellSize,
              backgroundColor: color || "transparent"
            }}
          />
        ))}
      </div>
    </div>
  );
}

export const PixelCharacter = memo(PixelCharacterInner);
