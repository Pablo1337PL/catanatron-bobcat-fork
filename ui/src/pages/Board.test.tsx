import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";

import { makeGameState } from "../test/fixtures";
import Board from "./Board";

test("renders the nested tile, node, and edge shapes emitted by GameEncoder", () => {
  const gameState = makeGameState();

  const { container } = render(
    <Board
      width={1200}
      height={900}
      buildOnNodeClick={() => () => undefined}
      buildOnEdgeClick={() => () => undefined}
      handleTileClick={() => undefined}
      replayMode={false}
      gameState={gameState}
      isMobile={false}
      show
      isMovingRobber={false}
    />
  );

  expect(container.querySelectorAll(".tile")).toHaveLength(3);
  expect(container.querySelectorAll(".node")).toHaveLength(1);
  expect(container.querySelectorAll(".edge")).toHaveLength(1);
  expect(container.querySelectorAll(".robber")).toHaveLength(1);
  expect(screen.getByText("11")).toBeInTheDocument();
  expect(screen.getByText("3:1")).toBeInTheDocument();
});

test("draws each land tile's letter unless turned off", () => {
  const gameState = makeGameState();
  gameState.tiles[0] = { ...gameState.tiles[0], label: "J" };
  const props = {
    width: 1200,
    height: 900,
    buildOnNodeClick: () => () => undefined,
    buildOnEdgeClick: () => () => undefined,
    handleTileClick: () => undefined,
    replayMode: false,
    gameState,
    isMobile: false,
    show: true,
    isMovingRobber: false,
  };

  const { container, rerender } = render(<Board {...props} />);
  expect(container.querySelectorAll(".tile-label")).toHaveLength(1);
  expect(container.querySelector(".tile-label")).toHaveTextContent("J");

  rerender(<Board {...props} showLabels={false} />);
  expect(container.querySelectorAll(".tile-label")).toHaveLength(0);
});

test("lights up the highlighted node, edge and tile only", () => {
  const gameState = makeGameState();
  const node = Object.values(gameState.nodes)[0];
  const edge = gameState.edges[0];
  const { container } = render(
    <Board
      width={1200}
      height={900}
      buildOnNodeClick={() => () => undefined}
      buildOnEdgeClick={() => () => undefined}
      handleTileClick={() => undefined}
      replayMode={false}
      gameState={gameState}
      isMobile={false}
      show
      isMovingRobber={false}
      highlight={{
        nodes: [node.id],
        edges: [[edge.id[1], edge.id[0]]],
        tiles: [gameState.tiles[0].coordinate],
      }}
    />
  );

  expect(container.querySelectorAll(".node .highlight")).toHaveLength(1);
  expect(container.querySelectorAll(".edge .highlight")).toHaveLength(1);
  expect(container.querySelectorAll(".tile.highlighted")).toHaveLength(1);
});
