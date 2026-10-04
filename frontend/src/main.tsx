import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import CssBaseline from "@mui/material/CssBaseline";
import "./index.css";
import App from "./App.tsx";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    {/* MUI's reset: normalizes box-sizing, body margin, background and the
        type scale. Without it MUI components render against raw browser
        defaults. */}
    <CssBaseline />
    <App />
  </StrictMode>,
);
