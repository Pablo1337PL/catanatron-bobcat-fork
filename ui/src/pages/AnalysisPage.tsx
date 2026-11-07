import { Button } from "@mui/material";

import PageTabs from "../components/PageTabs";

import "./HomePage.scss";
import "./AnalysisPage.scss";

/** What the analysis board will offer; none of it is built yet. */
const PLANNED_FEATURES = [
  ["Set up a position", "Place tiles, numbers, buildings, roads and the robber by hand."],
  ["Play both sides", "Make the moves of either player and explore the variations."],
  ["Load a game", "Open a finished game from a file and step through it."],
  ["Control the randomness", "Choose the dice roll, the next development card or what the robber steals."],
] as const;

/**
 * The analysis board, like a chess analysis board. A placeholder for now:
 * Start does nothing yet.
 */
export default function AnalysisPage() {
  return (
    <div className="home-page analysis-page">
      <div className="home-page__inner">
        <h1 className="logo">Catanatron</h1>
        <PageTabs />
        <div className="setup-card">
          <p className="setup-note">Analysis board · coming soon</p>
          <ul className="planned-features">
            {PLANNED_FEATURES.map(([title, description]) => (
              <li key={title}>
                <strong>{title}</strong>
                <span>{description}</span>
              </li>
            ))}
          </ul>
          <Button variant="contained" color="primary" className="start-btn">
            Start
          </Button>
        </div>
        <div className="page-end-spacer" aria-hidden="true" />
      </div>
    </div>
  );
}
