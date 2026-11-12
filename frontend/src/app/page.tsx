"use client";

import { Thread } from "@/components/thread";
import { StreamProvider } from "@/providers/Stream";
import { ProjectSessionProvider } from "@/providers/ProjectSession";
import { Toaster } from "@/components/ui/sonner";
import React from "react";

export default function DemoPage(): React.ReactNode {
  return (
    <React.Suspense fallback={<div>Loading (layout)...</div>}>
      <Toaster />
      <ProjectSessionProvider>
        <StreamProvider>
          <Thread />
        </StreamProvider>
      </ProjectSessionProvider>
    </React.Suspense>
  );
}
