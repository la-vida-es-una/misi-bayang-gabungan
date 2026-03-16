import { createRoot } from "react-dom/client";
import { MissionProvider } from "./store";
import { App } from "./App";

const root = document.getElementById("root");
if (root) {
  createRoot(root).render(
    <MissionProvider>
      <App />
    </MissionProvider>,
  );
}
