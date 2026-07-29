import React from "react";

export function Icon({ name, size = 20 }) {
  const url = `https://unpkg.com/lucide-static@0.462.0/icons/${name}.svg`;
  return (
    <span aria-hidden="true" style={{
      display: "inline-block", flex: "0 0 auto", width: size, height: size,
      backgroundColor: "currentColor",
      WebkitMaskImage: `url(${url})`, maskImage: `url(${url})`,
      WebkitMaskSize: "contain", maskSize: "contain",
      WebkitMaskRepeat: "no-repeat", maskRepeat: "no-repeat",
      WebkitMaskPosition: "center", maskPosition: "center",
    }} />
  );
}
