"use client";

import { useEffect, useState } from "react";

// Each element adds its own radius, so two radius utilities never meet.
const fill = "block bg-bg-active animate-pulse motion-reduce:animate-none";

/** Skeleton spec: the shape of an answer before its first part arrives, never shown for less
 * than 300 ms. The label is its accessible name. */
export function AnswerSkeleton() {
  const [shown, setShown] = useState(false);
  useEffect(() => {
    const timer = setTimeout(() => setShown(true), 300);
    return () => clearTimeout(timer);
  }, []);
  if (!shown) return null;
  return (
    <div
      role="status"
      aria-busy="true"
      aria-label="Loading the answer"
      className="flex flex-col gap-3"
    >
      <span className={`${fill} h-3 w-2/5 rounded-sm`} />
      <div className="flex flex-col gap-3.5 py-1.75">
        <span className={`${fill} h-3.5 w-full rounded-sm`} />
        <span className={`${fill} h-3.5 w-11/12 rounded-sm`} />
        <span className={`${fill} h-3.5 w-1/2 rounded-sm`} />
      </div>
      <div className="grid grid-cols-2 gap-2">
        <span className={`${fill} h-24 rounded-lg`} />
        <span className={`${fill} h-24 rounded-lg`} />
      </div>
    </div>
  );
}
