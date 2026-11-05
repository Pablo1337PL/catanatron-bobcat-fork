import { Fragment, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Alert,
  Button,
  Checkbox,
  IconButton,
  MenuItem,
  Select,
  Slider,
  TextField,
  Tooltip,
} from "@mui/material";
import HelpOutlineRoundedIcon from "@mui/icons-material/HelpOutlineRounded";
import SwapVertRoundedIcon from "@mui/icons-material/SwapVertRounded";
import { GridLoader } from "react-spinners";
import {
  createGame,
  getPlayers,
  type MapTemplate,
  type PlayerEntry,
  type PlayerKey,
} from "../utils/apiClient";

import "./HomePage.scss";

const MAP_TEMPLATES: MapTemplate[] = ["BASE", "MINI", "TOURNAMENT"];
const PLAYER_COLORS = ["RED", "BLUE", "ORANGE", "WHITE"] as const;
/** Default opponent of the Human: the first of these the server offers. */
const PREFERRED_OPPONENTS: PlayerKey[] = ["BOBCAT", "CATANATRON"];
const DEFAULT_PLAYERS: PlayerKey[] = ["HUMAN", "CATANATRON"];
const SEED_FIELDS = [
  ["boardSeed", "Board"],
  ["diceSeed", "Dice"],
  ["seed", "Game"],
] as const;
type SeedField = (typeof SEED_FIELDS)[number][0];

/** "" means random; otherwise a non-negative integer. */
function parseSeed(text: string): number | null | undefined {
  if (text.trim() === "") return null;
  return /^\d+$/.test(text.trim()) ? Number(text.trim()) : undefined;
}

export default function HomePage() {
  const [loading, setLoading] = useState(false);
  const [mapTemplate, setMapTemplate] = useState<MapTemplate>("BASE");
  const [vpsToWin, setVpsToWin] = useState(15);
  const [discardLimit, setDiscardLimit] = useState(9);
  const [friendlyRobber, setFriendlyRobber] = useState(true);
  const [players, setPlayers] = useState<PlayerKey[]>(DEFAULT_PLAYERS);
  const [randomSeats, setRandomSeats] = useState(false);
  const [seedTexts, setSeedTexts] = useState<Record<SeedField, string>>({
    seed: "",
    boardSeed: "",
    diceSeed: "",
  });
  const [available, setAvailable] = useState<PlayerEntry[]>([]);
  const navigate = useNavigate();

  // The server decides which players exist; the UI no longer hardcodes them.
  useEffect(() => {
    getPlayers()
      .then((entries) => {
        setAvailable(entries);
        const keys = new Set(entries.map((entry) => entry.key));
        const opponent = PREFERRED_OPPONENTS.find((key) => keys.has(key));
        if (opponent) {
          // Only while the user has not touched the list yet.
          setPlayers((current) =>
            current.join() === DEFAULT_PLAYERS.join()
              ? ["HUMAN", opponent]
              : current
          );
        }
      })
      .catch(() => setAvailable([]));
  }, []);

  const seeds = Object.fromEntries(
    SEED_FIELDS.map(([field]) => [field, parseSeed(seedTexts[field])])
  ) as Record<SeedField, number | null | undefined>;
  const hasInvalidSeed = Object.values(seeds).some(
    (value) => value === undefined
  );

  const humanKeys = useMemo(
    () => new Set(available.filter((entry) => !entry.is_bot).map((e) => e.key)),
    [available]
  );
  const isHuman = (key: PlayerKey) => humanKeys.has(key);
  const humanCount = players.filter(isHuman).length;
  const hasTooManyHumans = humanCount > 1;

  const handlePlayerChange = (index: number, value: PlayerKey) => {
    if (isHuman(value) && !isHuman(players[index]) && humanCount >= 1) {
      return;
    }

    setPlayers((current) =>
      current.map((player, playerIndex) =>
        playerIndex === index ? value : player
      )
    );
  };

  const handleAddPlayer = () => {
    setPlayers((current) =>
      current.length >= 4 ? current : [...current, "WEIGHTED_RANDOM"]
    );
  };

  /** Swaps the seats of players `index` and `index + 1`. */
  const handleSwapPlayers = (index: number) => {
    setPlayers((current) => {
      const next = [...current];
      [next[index], next[index + 1]] = [next[index + 1], next[index]];
      return next;
    });
  };

  const handleRemovePlayer = (index: number) => {
    setPlayers((current) =>
      current.length <= 2
        ? current
        : current.filter((_, playerIndex) => playerIndex !== index)
    );
  };

  const handleCreateGame = async () => {
    if (hasTooManyHumans || hasInvalidSeed) {
      return;
    }

    setLoading(true);
    const gameId = await createGame({
      players,
      mapTemplate,
      vpsToWin,
      discardLimit,
      friendlyRobber,
      randomSeats,
      seeds,
    });
    setLoading(false);
    navigate("/games/" + gameId);
  };

  return (
    <div className="home-page">
      <div className="home-page__inner">
        <h1 className="logo">Catanatron</h1>
        {!loading ? (
          <div className="setup-card">
            <p className="setup-note">Open hands. Random discard choice.</p>

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

            <div className="control-row">
              <div className="control-group compact-control">
                <div className="control-header">
                  <span>Points to Win</span>
                  <strong>{vpsToWin}</strong>
                </div>
                <Slider
                  value={vpsToWin}
                  min={3}
                  max={20}
                  step={1}
                  marks
                  valueLabelDisplay="auto"
                  onChange={(_, value) => setVpsToWin(value as number)}
                />
              </div>

              <div className="control-group compact-control">
                <div className="control-header">
                  <span>Card Discard Limit</span>
                  <strong>{discardLimit}</strong>
                </div>
                <Slider
                  value={discardLimit}
                  min={5}
                  max={20}
                  step={1}
                  marks
                  valueLabelDisplay="auto"
                  onChange={(_, value) => setDiscardLimit(value as number)}
                />
              </div>

              <div className="control-group compact-control switch-control">
                <div className="control-header">
                  <span className="inline-title">
                    Friendly Robber
                    <Tooltip
                      title="The robber may not be placed on tiles touching a player (opponent or yourself) with at most 2 visible victory points (victory point cards do not count)."
                      arrow
                      enterTouchDelay={0}
                      leaveTouchDelay={3000}
                    >
                      <IconButton
                        size="small"
                        className="help-button"
                        aria-label="Friendly Robber help"
                      >
                        <HelpOutlineRoundedIcon fontSize="inherit" />
                      </IconButton>
                    </Tooltip>
                  </span>
                  <strong>{friendlyRobber ? "On" : "Off"}</strong>
                </div>
                <Checkbox
                  className="inline-switch"
                  checked={friendlyRobber}
                  onChange={(event) =>
                    setFriendlyRobber(event.target.checked)
                  }
                />
              </div>
            </div>

            <div className="control-group">
              <div className="control-header">
                <span>Players</span>
                <strong>{players.length}/4</strong>
              </div>
              <label className="seat-option">
                <Checkbox
                  className="inline-switch"
                  checked={randomSeats}
                  onChange={(event) => setRandomSeats(event.target.checked)}
                />
                <span>Random seat order</span>
                <Tooltip
                  title="Off: Player 1 places first (1-2-2-1) and starts. On: the server draws the order."
                  arrow
                  enterTouchDelay={0}
                  leaveTouchDelay={3000}
                >
                  <IconButton
                    size="small"
                    className="help-button"
                    aria-label="Seat order help"
                  >
                    <HelpOutlineRoundedIcon fontSize="inherit" />
                  </IconButton>
                </Tooltip>
              </label>
              {hasTooManyHumans && (
                <Alert severity="error" className="players-alert">
                  Only one Human player is allowed.
                </Alert>
              )}
              <div className="players-list">
                {players.map((player, index) => (
                  <Fragment key={`${player}-${index}`}>
                  <div className="player-row">
                    <div className="player-meta">
                      <span className="player-label">
                        Player {index + 1}
                        {!randomSeats && index === 0 ? " · starts" : ""}
                      </span>
                      <span
                        className={`player-color-chip ${PLAYER_COLORS[index].toLowerCase()}`}
                      >
                        {PLAYER_COLORS[index]}
                      </span>
                    </div>
                    <Select
                      size="small"
                      fullWidth
                      value={player}
                      onChange={(event) =>
                        handlePlayerChange(
                          index,
                          event.target.value as PlayerKey
                        )
                      }
                    >
                      {available.map((option) => (
                        <MenuItem
                          key={option.key}
                          value={option.key}
                          disabled={
                            isHuman(option.key) &&
                            humanCount >= 1 &&
                            !isHuman(player)
                          }
                        >
                          {option.name}
                        </MenuItem>
                      ))}
                    </Select>
                    <Button
                      variant="text"
                      className="remove-player-btn"
                      disabled={players.length <= 2}
                      onClick={() => handleRemovePlayer(index)}
                    >
                      Remove
                    </Button>
                  </div>
                  {index < players.length - 1 && (
                    <div className="swap-row">
                      <Tooltip title={`Swap seats ${index + 1} and ${index + 2}`}>
                        <span>
                          <IconButton
                            size="small"
                            className="swap-button"
                            aria-label={`Swap seats ${index + 1} and ${index + 2}`}
                            disabled={randomSeats}
                            onClick={() => handleSwapPlayers(index)}
                          >
                            <SwapVertRoundedIcon fontSize="small" />
                          </IconButton>
                        </span>
                      </Tooltip>
                    </div>
                  )}
                  </Fragment>
                ))}
              </div>

              <Button
                variant="contained"
                className="add-player-btn"
                disabled={players.length >= 4}
                onClick={handleAddPlayer}
              >
                Add Player
              </Button>
            </div>

            <div className="control-group">
              <div className="control-header">
                <span className="inline-title">
                  Seeds
                  <Tooltip
                    title="Empty = random. The same seeds give the same board, the same dice and the same deck, so a game can be replayed. Board and dice are independent of each other."
                    arrow
                    enterTouchDelay={0}
                    leaveTouchDelay={3000}
                  >
                    <IconButton
                      size="small"
                      className="help-button"
                      aria-label="Seeds help"
                    >
                      <HelpOutlineRoundedIcon fontSize="inherit" />
                    </IconButton>
                  </Tooltip>
                </span>
                <strong>optional</strong>
              </div>
              <div className="seed-fields">
                {SEED_FIELDS.map(([field, label]) => (
                  <TextField
                    key={field}
                    size="small"
                    label={label}
                    placeholder="random"
                    value={seedTexts[field]}
                    error={seeds[field] === undefined}
                    helperText={
                      seeds[field] === undefined ? "Non-negative integer" : " "
                    }
                    slotProps={{ htmlInput: { inputMode: "numeric" } }}
                    onChange={(event) =>
                      setSeedTexts((current) => ({
                        ...current,
                        [field]: event.target.value,
                      }))
                    }
                  />
                ))}
              </div>
            </div>

            <Button
              variant="contained"
              color="primary"
              className="start-btn"
              disabled={hasTooManyHumans || hasInvalidSeed}
              onClick={handleCreateGame}
            >
              Start
            </Button>
          </div>
        ) : (
          <GridLoader
            className="loader"
            color="#ffffff"
            size={60}
          />
        )}
        <div className="page-end-spacer" aria-hidden="true" />
      </div>
    </div>
  );
}
