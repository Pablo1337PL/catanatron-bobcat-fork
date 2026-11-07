import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, expect, test } from "vitest";

import AnalysisPage from "./AnalysisPage";

afterEach(() => {
  cleanup();
});

function renderAt(path: string) {
  render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/analysis" element={<AnalysisPage />} />
        <Route path="/" element={<p>play page</p>} />
      </Routes>
    </MemoryRouter>
  );
}

test("the analysis tab lists what is planned and has a Start button", () => {
  renderAt("/analysis");

  expect(
    screen.getByRole("tab", { name: "Analysis", selected: true })
  ).toBeTruthy();
  expect(screen.getByText("Load a game")).toBeTruthy();
  expect(screen.getByText("Control the randomness")).toBeTruthy();
  expect(screen.getByRole("button", { name: "Start" })).toBeTruthy();
});

test("the Play tab leads back to the game setup", async () => {
  renderAt("/analysis");

  await userEvent.click(screen.getByRole("tab", { name: "Play" }));

  expect(screen.getByText("play page")).toBeTruthy();
});
