"use client";

import {
  useEffect,
  useRef,
  useState,
} from "react";

import { usePathname } from "next/navigation";

export default function NavigationProgress() {
  const pathname =
    usePathname();

  const firstRender =
    useRef(true);

  const [visible, setVisible] =
    useState(false);

  useEffect(() => {
    if (firstRender.current) {
      firstRender.current = false;
      return;
    }

    setVisible(true);

    const timer =
      window.setTimeout(() => {
        setVisible(false);
      }, 450);

    return () =>
      window.clearTimeout(timer);
  }, [pathname]);

  return (
    <div
      className={`globexa-route-progress ${
        visible
          ? "globexa-route-progress-visible"
          : ""
      }`}
      aria-hidden="true"
    >
      <span />
    </div>
  );
}