import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { createGame, getPlayers, type PlayerEntry } from "../utils/apiClient";
import HomePage from "./HomePage";

vi.mock("../utils/apiClient", () => ({
  createGame: vi.fn(),
  getPlayers: vi.fn(),
}));

function entry(key: string, isBot = true): PlayerEntry {
  return { key, name: key, description: "", is_bot: isBot, source: "", params: [] };
}

function renderPage(keys: string[]) {
  vi.mocked(getPlayers).mockResolvedValue(
    keys.map((key) => entry(key, key !== "HUMAN"))
  );
  render(
    <MemoryRouter>
      <HomePage />
    </MemoryRouter>
  );
}

async function start() {
  fireEvent.click(screen.getByRole("button", { name: "Start" }));
  await waitFor(() => expect(createGame).toHaveBeenCalled());
  return vi.mocked(createGame).mock.calls[0][0];
}

beforeEach(() => {
  vi.mocked(createGame).mockResolvedValue("game-id");
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

test("defaults to Human vs Bobcat when the server offers Bobcat", async () => {
  renderPage(["HUMAN", "CATANATRON", "BOBCAT"]);
  await screen.findByText("BOBCAT");
  expect(screen.getByText("Player 1 · starts")).toBeTruthy();
  expect((await start()).players).toEqual(["HUMAN", "BOBCAT"]);
});

test("falls back to Catanatron, fixed seats, random seeds", async () => {
  renderPage(["HUMAN", "CATANATRON"]);
  await screen.findByText("CATANATRON");
  const options = await start();
  expect(options.players).toEqual(["HUMAN", "CATANATRON"]);
  expect(options.randomSeats).toBe(false);
  expect(options.seeds).toEqual({ seed: null, boardSeed: null, diceSeed: null });
});

test("swap button exchanges seats", async () => {
  renderPage(["HUMAN", "BOBCAT"]);
  await screen.findByText("BOBCAT");
  fireEvent.click(screen.getByRole("button", { name: "Swap seats 1 and 2" }));
  expect((await start()).players).toEqual(["BOBCAT", "HUMAN"]);
});

test("random seat order disables swapping and is sent", async () => {
  renderPage(["HUMAN", "BOBCAT"]);
  await screen.findByText("BOBCAT");
  fireEvent.click(screen.getByRole("checkbox", { name: "Random seat order" }));
  expect(screen.getByRole("button", { name: "Swap seats 1 and 2" })).toBeDisabled();
  expect(screen.queryByText("Player 1 · starts")).toBeNull();
  expect((await start()).randomSeats).toBe(true);
});

test("seeds are sent, invalid ones block the start", async () => {
  renderPage(["HUMAN", "BOBCAT"]);
  await screen.findByText("BOBCAT");
  fireEvent.change(screen.getByLabelText("Board"), { target: { value: "-3" } });
  expect(screen.getByRole("button", { name: "Start" })).toBeDisabled();
  // Above 2^53 the number would be rounded and replay a different game.
  fireEvent.change(screen.getByLabelText("Board"), {
    target: { value: "4673525987207697974" },
  });
  expect(screen.getByRole("button", { name: "Start" })).toBeDisabled();
  fireEvent.change(screen.getByLabelText("Board"), { target: { value: "100" } });
  fireEvent.change(screen.getByLabelText("Dice"), { target: { value: "7" } });
  expect((await start()).seeds).toEqual({ seed: null, boardSeed: 100, diceSeed: 7 });
});

test("offers two fixed seats on the base or tournament board", async () => {
  renderPage(["HUMAN", "BOBCAT"]);
  await screen.findByText("BOBCAT");
  expect(screen.queryByRole("button", { name: "Add Player" })).toBeNull();
  expect(screen.queryByRole("button", { name: "Remove" })).toBeNull();
  expect(screen.queryByRole("button", { name: "MINI" })).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "TOURNAMENT" }));
  expect((await start()).mapTemplate).toBe("TOURNAMENT");
});
