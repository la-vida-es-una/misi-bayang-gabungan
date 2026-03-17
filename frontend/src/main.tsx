import { createRoot } from "react-dom/client";
import { MissionProvider } from "./store";
import { App } from "./App";
import { logInfo, logWarn } from "./logger";

const root = document.getElementById("root");
if (root) {
  logInfo("main", "Mounting React root");
  createRoot(root).render(
    <MissionProvider>
      <App />
    </MissionProvider>,
  );
} else {
  logWarn("main", "Root element not found");
}
