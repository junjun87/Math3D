import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import "./index.css";

// ======== PWA Service Worker 注册 ========
if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/sw.js").then(
      (registration) => {
        console.log("SW registered:", registration.scope);
      },
      (err) => {
        console.log("SW registration failed:", err);
      }
    );
  });
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
