import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Button, TextField } from "@mui/material";
import { enqueueSnackbar } from "notistack";

import PageTabs from "../components/PageTabs";
import {
  createGame,
  editGame,
  importGame,
  listGames,
  type MapTemplate,
  type StoredGameSummary,
} from "../utils/apiClient";

import "./HomePage.scss";
import "./AnalysisPage.scss";

const MAP_TEMPLATES: MapTemplate[] = ["BASE", "TOURNAMENT"];

export default function AnalysisPage() {
  const navigate = useNavigate();
  const [mapTemplate, setMapTemplate] = useState<MapTemplate>("BASE");
  const [boardSeed, setBoardSeed] = useState("");
  const [startEmptyBoard, setStartEmptyBoard] = useState(false);
  const [recentGames, setRecentGames] = useState<StoredGameSummary[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    listGames()
      .then(setRecentGames)
      .catch(() => setRecentGames([]));
  }, []);

  const handleStartSandbox = async () => {
    setLoading(true);
    try {
      const parsedBoardSeed =
        boardSeed.trim() !== "" && /^\d+$/.test(boardSeed.trim())
          ? Number(boardSeed.trim())
          : null;
      const gameId = await createGame({
        players: ["HUMAN", "HUMAN"],
        mapTemplate,
        vpsToWin: 15,
        discardLimit: 9,
        friendlyRobber: true,
        randomSeats: false,
        seeds: { boardSeed: parsedBoardSeed },
      });
      if (startEmptyBoard) {
        await editGame(gameId, { op: "clear_board" });
      }
      navigate(`/games/${gameId}`);
    } finally {
      setLoading(false);
    }
  };

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    try {
      const text = await file.text();
      const doc = JSON.parse(text);
      const newGameId = await importGame(doc, true);
      enqueueSnackbar("Loaded game into Analysis Board", {
        variant: "success",
      });
      navigate(`/games/${newGameId}`);
    } catch (err: any) {
      enqueueSnackbar(err?.message ?? "Invalid game file", {
        variant: "error",
      });
    }
  };

  return (
    <div className="home-page analysis-page">
      <div className="home-page__inner">
        <h1 className="logo">Catanatron</h1>
        <PageTabs />
        <div className="setup-card">
          <p className="setup-note">
            Analysis Board & Sandbox: Play both sides, edit positions, control
            dice & cards
          </p>

          <div className="control-group">
            <div className="control-header">
              <span>Map Template</span>
              <strong>{mapTemplate}</strong>
            </div>
            <div className="map-template-buttons">
              {MAP_TEMPLATES.map((value) => (
                <Button
                  key={value}
                  variant="contained"
                  onClick={() => setMapTemplate(value)}
                  className={`choice-button ${
                    mapTemplate === value ? "selected" : ""
                  }`}
                >
                  {value}
                </Button>
              ))}
            </div>
          </div>

          <div className="control-group">
            <div className="control-header">
              <span>Board Seed (optional)</span>
              <label style={{ fontSize: 12, cursor: "pointer", color: "#e6edf3" }}>
                <input
                  type="checkbox"
                  checked={startEmptyBoard}
                  onChange={(e) => setStartEmptyBoard(e.target.checked)}
                  style={{ marginRight: 6 }}
                />
                Start with clean position
              </label>
            </div>
            <TextField
              size="small"
              fullWidth
              placeholder="Random board seed (or enter integer)"
              value={boardSeed}
              onChange={(e) => setBoardSeed(e.target.value)}
            />
          </div>

          <Button
            variant="contained"
            color="primary"
            className="start-btn"
            disabled={loading}
            onClick={handleStartSandbox}
          >
            Start Analysis Board (Play Both Sides)
          </Button>

          <div className="control-group" style={{ marginTop: 16 }}>
            <div className="control-header">
              <span>Load Game from File (.json)</span>
            </div>
            <Button
              variant="outlined"
              component="label"
              fullWidth
              style={{ color: "#fff", borderColor: "rgba(255,255,255,0.25)" }}
            >
              Upload Game JSON File...
              <input
                type="file"
                accept=".json"
                hidden
                onChange={handleFileUpload}
              />
            </Button>
          </div>

          {recentGames.length > 0 && (
            <div className="control-group" style={{ marginTop: 12 }}>
              <div className="control-header">
                <span>Recent Games in Database</span>
                <strong>{recentGames.length}</strong>
              </div>
              <div
                style={{
                  maxHeight: 200,
                  overflowY: "auto",
                  display: "flex",
                  flexDirection: "column",
                  gap: 6,
                }}
              >
                {recentGames.map((g) => (
                  <div
                    key={g.game_id}
                    style={{
                      display: "flex",
                      justifyContent: "space-between",
                      alignItems: "center",
                      padding: "6px 10px",
                      background: "rgba(255,255,255,0.06)",
                      border: "1px solid rgba(255,255,255,0.1)",
                      borderRadius: 6,
                      fontSize: 12,
                      color: "#e6edf3",
                    }}
                  >
                    <div style={{ color: "#e6edf3" }}>
                      <strong style={{ color: "#ffffff" }}>{g.players.join(" vs ")}</strong> ·{" "}
                      <span>{g.state_index} moves</span> ·{" "}
                      <span>
                        RED {g.vps?.RED ?? 0} : {g.vps?.BLUE ?? 0} BLUE
                      </span>
                    </div>
                    <Button
                      size="small"
                      variant="contained"
                      onClick={() => navigate(`/games/${g.game_id}`)}
                    >
                      Open
                    </Button>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
        <div className="page-end-spacer" aria-hidden="true" />
      </div>
    </div>
  );
}
