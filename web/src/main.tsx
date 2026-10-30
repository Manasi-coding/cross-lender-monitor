import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Route, Routes } from "react-router";
import "./index.css";
import Label from "./Label";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<p className="p-4">Overview is built after the API (Day 7).</p>} />
        <Route path="/label" element={<Label />} />
      </Routes>
    </BrowserRouter>
  </StrictMode>,
);
