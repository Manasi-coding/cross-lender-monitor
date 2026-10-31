import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Route, Routes } from "react-router";
import "./index.css";
import App from "./App.jsx";
import Label from "./Label.jsx";
import { MetricsPage } from "./metrics.jsx";
import { BorrowerDetailPage, BorrowersPage, FilingsPage, OverviewPage } from "./pages.jsx";
import { ReviewPage } from "./review.jsx";
import { ComparisonPage, TriagePage } from "./triage.jsx";

// The labeling page is dev only: it is outside the shell and not in the nav. It works only when the API has ENABLE_LABELING=true.
createRoot(document.getElementById("root")).render(
  <StrictMode>
    <BrowserRouter>
      <Routes>
        <Route element={<App />}>
          <Route path="/" element={<OverviewPage />} />
          <Route path="/borrowers" element={<BorrowersPage />} />
          <Route path="/borrowers/:id" element={<BorrowerDetailPage />} />
          <Route path="/facilities" element={<TriagePage />} />
          <Route path="/facilities/:id" element={<ComparisonPage />} />
          <Route path="/review" element={<ReviewPage />} />
          <Route path="/metrics" element={<MetricsPage />} />
          <Route path="/filings" element={<FilingsPage />} />
          <Route path="*" element={<p>This page does not exist.</p>} />
        </Route>
        <Route path="/label" element={<Label />} />
      </Routes>
    </BrowserRouter>
  </StrictMode>,
);
